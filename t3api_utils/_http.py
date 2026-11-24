"""The httpx2 client builder: retry transport, rate limiting, redacted logging."""

from __future__ import annotations

import email.utils
import json
import logging
import os
import random
import re
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping
from importlib import metadata
from typing import Any
from urllib.parse import urlsplit

import httpx2

from t3api_utils._ratelimit import TokenBucket

DEFAULT_HOST = "https://api.trackandtrace.tools"
DEFAULT_TIMEOUT = 30.0
REPORT_TIMEOUT = 300.0
MAX_ATTEMPTS = 3
BACKOFF = 0.5
MAX_RETRY_AFTER = 60.0

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
RETRY_STATUSES_IDEMPOTENT = frozenset({429, 502, 503, 504})
RETRY_STATUSES_WRITE = frozenset({429})

# Connection failures that happen before any request bytes are sent, so even
# a write can safely be retried.
PRE_SEND_ERRORS: tuple[type[Exception], ...] = (
    httpx2.ConnectError,
    httpx2.ConnectTimeout,
    httpx2.PoolTimeout,
)

SENSITIVE_HEADERS = frozenset({"authorization", "x-t3-api-key", "cookie", "set-cookie"})
SENSITIVE_FIELDS = frozenset(
    {"password", "otp", "otpseed", "secretkey", "accesstoken", "refreshtoken"}
)
_SECRET_PATH = re.compile(r"(/v2/auth/secretkey/)[^/?#]+", re.IGNORECASE)
_SECRET_QUERY = re.compile(r"([?&]secretKey=)[^&#]*", re.IGNORECASE)
_MAX_LOGGED_BODY = 4000

logger = logging.getLogger("t3api_utils")
http_logger = logging.getLogger("t3api_utils.http")


def user_agent() -> str:
    try:
        version = metadata.version("t3api-utils")
    except metadata.PackageNotFoundError:  # pragma: no cover - only in odd installs
        version = "unknown"
    return f"t3api-utils/{version}"


# --------------------------------------------------------------------------- redaction


def redact_url(url: str) -> str:
    """Mask a secret key in a /v2/auth/secretkey/{key} path or ?secretKey= query."""
    url = _SECRET_PATH.sub(r"\1***", url)
    return _SECRET_QUERY.sub(r"\1***", url)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: ("***" if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()}


def redact_json(value: Any) -> Any:
    """Mask password, OTP, OTP seed, secret key and token fields, at any depth."""
    if isinstance(value, dict):
        return {
            k: ("***" if isinstance(k, str) and k.lower() in SENSITIVE_FIELDS else redact_json(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_json(v) for v in value]
    return value


def _redact_body(raw: bytes, content_type: str) -> str:
    if not raw:
        return ""
    if "json" in content_type:
        try:
            text = json.dumps(redact_json(json.loads(raw)), ensure_ascii=False)
        except (ValueError, UnicodeDecodeError):
            text = "<unparseable JSON body>"
    elif "form" in content_type:
        return "<form body not logged>"
    else:
        try:
            text = raw.decode()
        except UnicodeDecodeError:
            return f"<{len(raw)} bytes>"
    if len(text) > _MAX_LOGGED_BODY:
        text = text[:_MAX_LOGGED_BODY] + "…"
    return text


# --------------------------------------------------------------------------- retries


def _retry_after(response: httpx2.Response, now: Callable[[], float] = time.time) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        seconds = parsed.timestamp() - now()
    return float(max(0.0, min(seconds, MAX_RETRY_AFTER)))


class RetryTransport(httpx2.BaseTransport):
    """Retries what is safe to retry, and rate-limits every attempt.

    GET, HEAD and OPTIONS retry on connection errors and 429, 502, 503, 504.
    Writes retry only on 429 and on connection failures before the request was
    sent: a 5xx or a read timeout may mean the write already reached Metrc.
    """

    def __init__(
        self,
        wrapped: httpx2.BaseTransport,
        *,
        limiter: TokenBucket | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        backoff: float = BACKOFF,
        sleep: Callable[[float], None] | None = None,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.wrapped = wrapped
        self.limiter = limiter
        self.max_attempts = max(1, max_attempts)
        self.backoff = backoff
        self._sleep = sleep
        self._jitter = jitter

    def _delay(self, attempt: int) -> float:
        base = self.backoff * float(2 ** (attempt - 1))
        return base * (0.75 + 0.5 * self._jitter())

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        idempotent = request.method.upper() in IDEMPOTENT_METHODS
        statuses = RETRY_STATUSES_IDEMPOTENT if idempotent else RETRY_STATUSES_WRITE
        attempt = 1
        while True:
            if self.limiter is not None:
                self.limiter.acquire()
            try:
                response = self.wrapped.handle_request(request)
            except httpx2.TransportError as exc:
                retryable = idempotent or isinstance(exc, PRE_SEND_ERRORS)
                if not retryable or attempt >= self.max_attempts:
                    raise
                delay = self._delay(attempt)
                logger.warning(
                    "%s %s failed (%s); retrying in %.1fs (attempt %d of %d)",
                    request.method,
                    redact_url(str(request.url)),
                    type(exc).__name__,
                    delay,
                    attempt + 1,
                    self.max_attempts,
                )
            else:
                if response.status_code not in statuses or attempt >= self.max_attempts:
                    return response
                retry_after = _retry_after(response)
                delay = self._delay(attempt) if retry_after is None else retry_after
                response.close()
                logger.warning(
                    "%s %s returned %d; retrying in %.1fs (attempt %d of %d)",
                    request.method,
                    redact_url(str(request.url)),
                    response.status_code,
                    delay,
                    attempt + 1,
                    self.max_attempts,
                )
            (self._sleep or time.sleep)(delay)
            attempt += 1

    def close(self) -> None:
        self.wrapped.close()


# --------------------------------------------------------------------------- logging


def _log_request(request: httpx2.Request) -> None:
    if not http_logger.isEnabledFor(logging.DEBUG):
        return
    content_type = request.headers.get("content-type", "")
    try:
        body = _redact_body(request.content, content_type)
    except httpx2.RequestNotRead:
        body = "<streamed body>"
    http_logger.debug(
        "→ %s %s headers=%s body=%s",
        request.method,
        redact_url(str(request.url)),
        redact_headers(request.headers),
        body,
    )


def _log_response(response: httpx2.Response) -> None:
    if not http_logger.isEnabledFor(logging.DEBUG):
        return
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        response.read()
        body = _redact_body(response.content, content_type)
    else:
        body = f"<{content_type or 'unknown'} body not logged>"
    http_logger.debug(
        "← %d %s %s headers=%s body=%s",
        response.status_code,
        response.request.method,
        redact_url(str(response.request.url)),
        redact_headers(response.headers),
        body,
    )


_handler_installed = False


def enable_http_logging(log_file: str | None = None) -> None:
    """Turn on DEBUG request/response logging for ``t3api_utils.http``.

    This only runs when asked for (``log_http=True`` or ``T3_LOG_HTTP=1``). It
    adds a handler only when a log file is named, or when nothing else would
    print the messages.
    """
    global _handler_installed
    http_logger.setLevel(logging.DEBUG)
    if _handler_installed:
        return
    handler: logging.Handler | None = None
    if log_file:
        handler = logging.FileHandler(log_file, encoding="utf-8")
    elif not http_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stderr)
    if handler is not None:
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        http_logger.addHandler(handler)
        _handler_installed = True


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------- client


def env_proxy(base_url: str) -> str | None:
    """The proxy from HTTPS_PROXY / HTTP_PROXY / ALL_PROXY for ``base_url``, honoring NO_PROXY.

    httpx2 reads these itself only when it builds its own transport. Ours wraps
    the transport for retries, so the environment is read here instead.
    """
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    no_proxy = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or ""
    for entry in (e.strip().lower() for e in no_proxy.split(",")):
        name = entry.split(":", 1)[0].lstrip(".")
        if entry == "*" or (name and (host == name or host.endswith("." + name))):
            return None
    proxies = urllib.request.getproxies_environment()
    return proxies.get(parts.scheme or "https") or proxies.get("all") or None


def build_client(
    *,
    base_url: str = DEFAULT_HOST,
    auth: httpx2.Auth | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    rate_limit: float | None = None,
    log_http: bool = False,
    transport: httpx2.BaseTransport | None = None,
    verify: bool | str = True,
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> httpx2.Client:
    """Build the configured ``httpx2.Client`` every T3Client uses.

    ``transport`` swaps the network layer (tests pass ``httpx2.MockTransport``).
    Retries and rate limiting wrap whatever transport is used.
    """
    if log_http:
        enable_http_logging(os.environ.get("T3_LOG_FILE") or None)
    if transport is None:
        transport = httpx2.HTTPTransport(verify=verify, proxy=proxy or env_proxy(base_url))
    inner = transport
    limiter = TokenBucket(rate_limit) if rate_limit else None
    merged = {"User-Agent": user_agent(), "Accept": "application/json"}
    merged.update(headers or {})
    return httpx2.Client(
        base_url=base_url.rstrip("/"),
        auth=auth,
        timeout=timeout,
        headers=merged,
        transport=RetryTransport(inner, limiter=limiter, sleep=sleep),
        event_hooks={"request": [_log_request], "response": [_log_response]},
    )
