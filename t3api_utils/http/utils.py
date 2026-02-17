"""Reusable HTTP utilities for t3api-utils (sync + async).

Scope (by design)
------------------
Configures and performs network activity (clients, retries, JSON handling, 
headers, SSL, proxies)

Highlights
----------
- Centralized `httpx` client builders (sync + async) with sane defaults
  (timeout, HTTP/2, SSL via `certifi`, base headers, optional proxies).
- Lightweight retry policy with exponential backoff + jitter.
- Standard JSON request helpers with consistent error text.
- Simple helpers to attach/remove Bearer tokens *without* performing auth.
- Optional request/response logging hooks.

Examples
--------
Sync client with bearer token:
    from t3api_utils.http import build_client, set_bearer_token, request_json

    client = build_client()
    set_bearer_token(client=client, token="<token>")
    data = request_json(client=client, method="GET", url="/v2/auth/whoami")

Async with logging hooks:
    from t3api_utils.http import build_async_client, arequest_json, LoggingHooks

    hooks = LoggingHooks(enabled=True)
    async with build_async_client(hooks=hooks) as aclient:
        data = await arequest_json(aclient=aclient, method="GET", url="/healthz")

"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import (Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple,
                    Union)

import ssl
import certifi
import httpx
from httpx._types import RequestFiles

# Import config manager for default values
from t3api_utils.cli.utils import config_manager

__all__ = [
    "HTTPConfig",
    "RetryPolicy",
    "LoggingHooks",
    "T3HTTPError",
    "build_client",
    "build_async_client",
    "request_json",
    "arequest_json",
    "set_bearer_token",
    "clear_bearer_token",
]


log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_USER_AGENT = "t3api-utils/py (unknown-version)"


def _create_ssl_context(verify: Union[bool, str]) -> Union[bool, ssl.SSLContext]:
    """Create proper SSL context for httpx to avoid deprecation warnings."""
    if isinstance(verify, bool):
        return verify
    if isinstance(verify, str):
        return ssl.create_default_context(cafile=verify)
    return verify


def _get_default_host() -> str:
    """Get default API host from configuration."""
    return config_manager.get_api_host()


@dataclass(frozen=True)
class HTTPConfig:
    """Base HTTP client configuration (no routes).

    Attributes:
        host: Base URL of the API server (e.g. ``"https://api.example.com"``).
            Defaults to the value returned by the config manager.
        timeout: Request timeout in seconds. Defaults to ``DEFAULT_TIMEOUT``.
        verify_ssl: SSL verification setting. Pass ``True`` to use default
            CA bundle, ``False`` to disable verification, or a file path to
            a custom CA certificate. Defaults to the ``certifi`` CA bundle.
        base_headers: Default headers attached to every request built by
            this configuration. Defaults to a ``User-Agent`` header.
        proxies: Optional proxy URL string or mapping of scheme to proxy
            URL (e.g. ``{"https://": "http://proxy:8080"}``).
    """

    host: str = field(default_factory=_get_default_host)
    timeout: float = DEFAULT_TIMEOUT
    verify_ssl: Union[bool, str] = certifi.where()
    base_headers: Mapping[str, str] = field(default_factory=lambda: {"User-Agent": DEFAULT_USER_AGENT})
    proxies: Optional[Union[str, Mapping[str, str]]] = None

    @property
    def ssl_context(self) -> Union[bool, ssl.SSLContext]:
        """Get proper SSL context for httpx."""
        return _create_ssl_context(self.verify_ssl)


@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy for transient failures. Route-agnostic.

    Note: writes (POST/PUT/PATCH/DELETE) are included by default. If your call
    is not idempotent, provide a custom policy at the callsite.

    Attributes:
        max_attempts: Maximum number of attempts (including the initial
            request). Defaults to ``3``.
        backoff_factor: Base delay in seconds for exponential backoff.
            Actual sleep is ``backoff_factor * 2^(attempt - 2)`` with
            +/- 20 % jitter. Defaults to ``0.5``.
        retry_methods: HTTP methods eligible for automatic retry.
            Defaults to all standard methods.
        retry_statuses: HTTP status codes that trigger a retry.
            Defaults to common transient-error codes (408, 409, 425,
            429, 500, 502, 503, 504).
    """

    max_attempts: int = 3
    backoff_factor: float = 0.5  # seconds; exponential backoff
    retry_methods: Sequence[str] = (
        "GET",
        "HEAD",
        "OPTIONS",
        "DELETE",
        "PUT",
        "PATCH",
        "POST",
    )
    retry_statuses: Sequence[int] = (408, 409, 425, 429, 500, 502, 503, 504)


_SENSITIVE_HEADERS = frozenset({
    "authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization",
})

_MAX_BODY_LOG_LENGTH = 2000

_http_debug_log = logging.getLogger("t3api_utils.http.debug")


def _mask_header_value(name: str, value: str) -> str:
    """Mask sensitive header values, preserving a prefix and suffix for debugging."""
    if name.lower() not in _SENSITIVE_HEADERS:
        return value
    if len(value) < 12:
        return "****"
    return value[:8] + "****" + value[-4:]


def _format_headers(headers: Mapping[str, str]) -> str:
    """Format headers as indented key: value lines with sensitive values masked."""
    lines = []
    for name, value in headers.items():
        lines.append(f"  {name}: {_mask_header_value(name, value)}")
    return "\n".join(lines)


def _format_body(content: Optional[bytes]) -> str:
    """Format a request body for logging, pretty-printing JSON when possible."""
    if not content:
        return "  (empty)"
    try:
        parsed = json.loads(content)
        text = json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, UnicodeDecodeError):
        text = content.decode("utf-8", errors="replace")
    if len(text) > _MAX_BODY_LOG_LENGTH:
        text = text[:_MAX_BODY_LOG_LENGTH] + "\n  ... (truncated)"
    # Indent each line for readability
    return "\n".join(f"  {line}" for line in text.splitlines())


@dataclass(frozen=True)
class LoggingHooks:
    """Optional request/response logging via httpx event hooks.

    Attributes:
        enabled: When ``True``, debug-level log messages are emitted for
            every outgoing request and incoming response. Defaults to
            ``False``.
        log_headers: When ``True`` and logging is enabled, request headers
            are included in log output. Sensitive headers are masked.
        log_body: When ``True`` and logging is enabled, request bodies
            are included in log output (JSON is pretty-printed).
        file_path: Optional file path for HTTP debug logs. The file is
            opened in write mode (truncated) on first use.
    """

    enabled: bool = False
    log_headers: bool = True
    log_body: bool = True
    file_path: Optional[str] = None

    @classmethod
    def from_env(cls) -> LoggingHooks:
        """Create a ``LoggingHooks`` instance configured from environment variables.

        Reads ``T3_LOG_HTTP``, ``T3_LOG_HEADERS``, ``T3_LOG_BODY``, and
        ``T3_LOG_FILE`` from the environment.

        Returns:
            A configured ``LoggingHooks`` instance. If ``T3_LOG_HTTP`` is
            not set or is falsy, returns a disabled instance.
        """
        import os
        enabled = os.getenv("T3_LOG_HTTP", "").lower() in ("true", "1", "yes", "on")
        if not enabled:
            return cls(enabled=False)

        log_headers = os.getenv("T3_LOG_HEADERS", "true").lower() not in ("false", "0", "no", "off")
        log_body = os.getenv("T3_LOG_BODY", "true").lower() not in ("false", "0", "no", "off")
        file_path = os.getenv("T3_LOG_FILE", "").strip() or None

        return cls(
            enabled=True,
            log_headers=log_headers,
            log_body=log_body,
            file_path=file_path,
        )

    def _get_logger(self) -> logging.Logger:
        """Get the configured debug logger, setting up file handler if needed."""
        logger = _http_debug_log

        # Only add file handler once
        if self.file_path and not any(
            isinstance(h, logging.FileHandler) and getattr(h, '_t3_debug_path', None) == self.file_path
            for h in logger.handlers
        ):
            handler = logging.FileHandler(self.file_path, mode="w", encoding="utf-8")
            handler._t3_debug_path = self.file_path  # type: ignore[attr-defined]
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            ))
            handler.setLevel(logging.DEBUG)
            logger.addHandler(handler)

        logger.setLevel(logging.DEBUG)
        return logger

    def as_hooks(self, *, async_client: bool = False) -> Optional[Dict[str, Any]]:
        """Build an httpx ``event_hooks`` mapping for request/response logging.

        Args:
            async_client: When ``True``, returns async hook callables
                suitable for ``httpx.AsyncClient``. When ``False``
                (default), returns synchronous callables for
                ``httpx.Client``.

        Returns:
            A dict with ``"request"`` and ``"response"`` hook lists, or
            ``None`` if logging is disabled.
        """
        if not self.enabled:
            return None

        debug_logger = self._get_logger()
        do_headers = self.log_headers
        do_body = self.log_body

        def _build_request_message(request: httpx.Request) -> str:
            parts = [f">>> HTTP {request.method} {request.url}"]
            if do_headers:
                parts.append(f"  Headers:\n{_format_headers(request.headers)}")
            if do_body and request.content:
                parts.append(f"  Body:\n{_format_body(request.content)}")
            return "\n".join(parts)

        def _build_response_message(response: httpx.Response) -> str:
            req = response.request
            return f"<<< HTTP {req.method} {req.url} -> {response.status_code}"

        async def _alog_request(request: httpx.Request) -> None:
            debug_logger.debug(_build_request_message(request))

        async def _alog_response(response: httpx.Response) -> None:
            debug_logger.debug(_build_response_message(response))

        def _log_request(request: httpx.Request) -> None:
            debug_logger.debug(_build_request_message(request))

        def _log_response(response: httpx.Response) -> None:
            debug_logger.debug(_build_response_message(response))

        if async_client:
            return {
                "request": [_alog_request],
                "response": [_alog_response],
            }
        else:
            return {
                "request": [_log_request],
                "response": [_log_response],
            }


class T3HTTPError(httpx.HTTPError):
    """Raised when a request fails permanently or response parsing fails."""

    def __init__(
        self, message: str, *, response: Optional[httpx.Response] = None
    ) -> None:
        """Initialize a T3HTTPError.

        Args:
            message: Human-readable description of the failure.
            response: The ``httpx.Response`` that caused the error, if
                available. Retained for callers that need to inspect
                status codes or response bodies.
        """
        super().__init__(message)
        self.response = response

    @property
    def status_code(self) -> Optional[int]:
        """HTTP status code from the stored response, or ``None`` if unavailable."""
        return self.response.status_code if self.response is not None else None


# ----------------------
# Client builders
# ----------------------


def _merge_headers(
    base: Mapping[str, str], extra: Optional[Mapping[str, str]]
) -> Dict[str, str]:
    """Merge base headers with optional extra headers.

    Extra headers take precedence over base headers. Keys in ``extra``
    whose value is ``None`` are silently dropped.

    Args:
        base: Default headers (typically from ``HTTPConfig.base_headers``).
        extra: Additional headers to layer on top. May be ``None``.

    Returns:
        Merged header dictionary.
    """
    if not extra:
        return dict(base)
    # Prefer extra headers when not None
    return {**base, **{k: v for k, v in extra.items() if v is not None}}


def build_client(
    *,
    config: Optional[HTTPConfig] = None,
    headers: Optional[Mapping[str, str]] = None,
    hooks: Optional[LoggingHooks] = None,
) -> httpx.Client:
    """Construct a configured ``httpx.Client`` with sane defaults.

    Args:
        config: HTTP configuration (host, timeout, SSL, proxies).
            Defaults to ``HTTPConfig()`` when ``None``.
        headers: Extra headers merged on top of ``config.base_headers``.
        hooks: Optional logging hooks attached as httpx event hooks.

    Returns:
        A ready-to-use ``httpx.Client`` instance.
    """
    cfg = config or HTTPConfig()
    merged_headers = _merge_headers(cfg.base_headers, headers)

    return httpx.Client(
        base_url=cfg.host.rstrip("/"),
        timeout=cfg.timeout,
        verify=cfg.ssl_context,
        headers=merged_headers,
        proxy=cfg.proxies,  # type: ignore[arg-type]
        http2=False,
        event_hooks=(hooks.as_hooks(async_client=False) if hooks else None),
    )


def build_async_client(
    *,
    config: Optional[HTTPConfig] = None,
    headers: Optional[Mapping[str, str]] = None,
    hooks: Optional[LoggingHooks] = None,
) -> httpx.AsyncClient:
    """Construct a configured ``httpx.AsyncClient`` with sane defaults.

    Args:
        config: HTTP configuration (host, timeout, SSL, proxies).
            Defaults to ``HTTPConfig()`` when ``None``.
        headers: Extra headers merged on top of ``config.base_headers``.
        hooks: Optional logging hooks attached as httpx event hooks.

    Returns:
        A ready-to-use ``httpx.AsyncClient`` instance. Should be used as
        an async context manager or closed explicitly when finished.
    """
    cfg = config or HTTPConfig()
    merged_headers = _merge_headers(cfg.base_headers, headers)

    return httpx.AsyncClient(
        base_url=cfg.host.rstrip("/"),
        timeout=cfg.timeout,
        verify=cfg.ssl_context,
        headers=merged_headers,
        proxy=cfg.proxies,  # type: ignore[arg-type]
        http2=False,
        event_hooks=(hooks.as_hooks(async_client=True) if hooks else None),
    )


# ----------------------
# Core request helpers
# ----------------------


def _should_retry(
    *,
    policy: RetryPolicy,
    attempt: int,
    method: str,
    exc: Optional[Exception],
    resp: Optional[httpx.Response],
) -> bool:
    """Determine whether a failed request should be retried.

    A retry is allowed when:
    - The current attempt number is below ``policy.max_attempts``.
    - The HTTP method is listed in ``policy.retry_methods``.
    - Either a transport-level exception occurred, or the response status
      code is in ``policy.retry_statuses``.

    Args:
        policy: The active retry policy.
        attempt: Current attempt number (1-indexed).
        method: HTTP method of the request (e.g. ``"GET"``).
        exc: Transport/network exception, if any.
        resp: HTTP response, if one was received.

    Returns:
        ``True`` if the request should be retried, ``False`` otherwise.
    """
    if attempt >= policy.max_attempts:
        return False

    if method.upper() not in policy.retry_methods:
        return False

    if exc is not None:
        # Network/transport-level issues: retry
        return True

    if resp is not None and resp.status_code in policy.retry_statuses:
        return True

    return False


def _sleep_with_backoff(policy: RetryPolicy, attempt: int) -> None:
    """Sleep using exponential backoff with jitter (synchronous).

    No sleep is performed on the first attempt. Subsequent attempts sleep
    for ``backoff_factor * 2^(attempt - 2)`` seconds, plus or minus 20 %
    random jitter.

    Args:
        policy: Retry policy supplying the backoff factor.
        attempt: Current attempt number (1-indexed).
    """
    if attempt <= 1:
        return
    delay = policy.backoff_factor * (2 ** (attempt - 2))
    jitter = delay * 0.2
    time.sleep(max(0.0, delay + random.uniform(-jitter, jitter)))


async def _async_sleep_with_backoff(policy: RetryPolicy, attempt: int) -> None:
    """Sleep using exponential backoff with jitter (asynchronous).

    Async equivalent of :func:`_sleep_with_backoff`. Uses
    ``asyncio.sleep`` so the event loop is not blocked.

    Args:
        policy: Retry policy supplying the backoff factor.
        attempt: Current attempt number (1-indexed).
    """
    if attempt <= 1:
        return
    delay = policy.backoff_factor * (2 ** (attempt - 2))
    jitter = delay * 0.2
    await asyncio.sleep(max(0.0, delay + random.uniform(-jitter, jitter)))


def _format_http_error_message(resp: httpx.Response) -> str:
    """Build a human-readable error string from an HTTP response.

    Attempts to extract a message from well-known JSON keys
    (``message``, ``detail``, ``error``, ``errors``). Falls back to
    the raw response text, truncated to 2048 characters.

    Args:
        resp: The ``httpx.Response`` that triggered the error.

    Returns:
        Formatted error string prefixed with the HTTP status code.
    """
    # Prefer common JSON keys when available
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            for key in ("message", "detail", "error", "errors"):
                if key in payload:
                    return f"HTTP {resp.status_code}: {payload[key]}"
        return f"HTTP {resp.status_code}: {payload}"
    except Exception:
        text = resp.text or ""
        if len(text) > 2048:
            text = text[:2048] + "…"
        return f"HTTP {resp.status_code}: {text or '<no body>'}"


def request_json(
    *,
    client: httpx.Client,
    method: str,
    url: str,
    params: Optional[Mapping[str, Any]] = None,
    json_body: Optional[Any] = None,
    files: Optional[RequestFiles] = None,
    headers: Optional[Mapping[str, str]] = None,
    policy: Optional[RetryPolicy] = None,
    expected_status: Union[int, Iterable[int]] = (200, 201, 202, 204),
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    request_id: Optional[str] = None,
) -> Any:
    """Issue a synchronous JSON request with automatic retries.

    Sends the request via the provided ``httpx.Client``, retrying on
    transient failures according to the supplied (or default) retry
    policy. The response body is parsed as JSON and returned.

    Args:
        client: An ``httpx.Client`` (typically from :func:`build_client`).
        method: HTTP method (e.g. ``"GET"``, ``"POST"``).
        url: Request URL or path (resolved against the client's base URL).
        params: Optional query-string parameters.
        json_body: Optional JSON-serializable request body. Mutually
            exclusive with *files*.
        files: Optional multipart file upload data. Mutually exclusive
            with *json_body*. Accepts the same formats as ``httpx``'s
            ``files`` parameter (e.g.
            ``{"field": ("name.png", data, "image/png")}``).
        headers: Optional per-request headers merged on top of the
            client's default headers.
        policy: Retry policy. Defaults to ``RetryPolicy()`` when ``None``.
        expected_status: Status code(s) considered successful. Defaults
            to ``(200, 201, 202, 204)``.
        timeout: Per-request timeout override. ``None`` uses the client
            default.
        request_id: Optional value set as the ``X-Request-ID`` header
            (unless already present in *headers*).

    Returns:
        Parsed JSON response body, or ``None`` for 204 / empty responses.

    Raises:
        ValueError: If both *json_body* and *files* are provided.
        T3HTTPError: If the response status is not in *expected_status*
            after all retries are exhausted, or if the response body
            cannot be decoded as JSON.
    """
    if json_body is not None and files is not None:
        raise ValueError("json_body and files are mutually exclusive; provide one or neither.")

    pol = policy or RetryPolicy()
    exp: Tuple[int, ...] = (
        (expected_status,) if isinstance(expected_status, int) else tuple(expected_status)
    )

    # Merge headers + optional request id
    merged_headers = dict(headers or {})
    if request_id and "X-Request-ID" not in merged_headers:
        merged_headers["X-Request-ID"] = request_id

    attempt = 0
    while True:
        attempt += 1
        try:
            resp = client.request(
                method.upper(),
                url,
                params=params,
                json=json_body,
                files=files,
                headers=merged_headers or None,
                timeout=timeout,
            )
            if resp.status_code not in exp:
                if _should_retry(policy=pol, attempt=attempt, method=method, exc=None, resp=resp):
                    _sleep_with_backoff(pol, attempt)
                    continue
                raise T3HTTPError(_format_http_error_message(resp), response=resp)

            if resp.status_code == 204:
                return None
            if not resp.content:
                return None
            try:
                return resp.json()
            except json.JSONDecodeError as e:
                raise T3HTTPError("Failed to decode JSON response.", response=resp) from e
        except httpx.HTTPError as e:
            if _should_retry(policy=pol, attempt=attempt, method=method, exc=e, resp=None):
                _sleep_with_backoff(pol, attempt)
                continue
            raise T3HTTPError(str(e)) from e


async def arequest_json(
    *,
    aclient: httpx.AsyncClient,
    method: str,
    url: str,
    params: Optional[Mapping[str, Any]] = None,
    json_body: Optional[Any] = None,
    files: Optional[RequestFiles] = None,
    headers: Optional[Mapping[str, str]] = None,
    policy: Optional[RetryPolicy] = None,
    expected_status: Union[int, Iterable[int]] = (200, 201, 202, 204),
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    request_id: Optional[str] = None,
) -> Any:
    """Issue an asynchronous JSON request with automatic retries.

    Async equivalent of :func:`request_json`. Sends the request via the
    provided ``httpx.AsyncClient``, retrying on transient failures
    according to the supplied (or default) retry policy.

    Args:
        aclient: An ``httpx.AsyncClient`` (typically from
            :func:`build_async_client`).
        method: HTTP method (e.g. ``"GET"``, ``"POST"``).
        url: Request URL or path (resolved against the client's base URL).
        params: Optional query-string parameters.
        json_body: Optional JSON-serializable request body. Mutually
            exclusive with *files*.
        files: Optional multipart file upload data. Mutually exclusive
            with *json_body*. Accepts the same formats as ``httpx``'s
            ``files`` parameter.
        headers: Optional per-request headers merged on top of the
            client's default headers.
        policy: Retry policy. Defaults to ``RetryPolicy()`` when ``None``.
        expected_status: Status code(s) considered successful. Defaults
            to ``(200, 201, 202, 204)``.
        timeout: Per-request timeout override. ``None`` uses the client
            default.
        request_id: Optional value set as the ``X-Request-ID`` header
            (unless already present in *headers*).

    Returns:
        Parsed JSON response body, or ``None`` for 204 / empty responses.

    Raises:
        ValueError: If both *json_body* and *files* are provided.
        T3HTTPError: If the response status is not in *expected_status*
            after all retries are exhausted, or if the response body
            cannot be decoded as JSON.
    """
    if json_body is not None and files is not None:
        raise ValueError("json_body and files are mutually exclusive; provide one or neither.")

    pol = policy or RetryPolicy()
    exp: Tuple[int, ...] = (
        (expected_status,) if isinstance(expected_status, int) else tuple(expected_status)
    )

    # Merge headers + optional request id
    merged_headers = dict(headers or {})
    if request_id and "X-Request-ID" not in merged_headers:
        merged_headers["X-Request-ID"] = request_id

    attempt = 0
    while True:
        attempt += 1
        try:
            resp = await aclient.request(
                method.upper(),
                url,
                params=params,
                json=json_body,
                files=files,
                headers=merged_headers or None,
                timeout=timeout,
            )
            if resp.status_code not in exp:
                if _should_retry(policy=pol, attempt=attempt, method=method, exc=None, resp=resp):
                    await _async_sleep_with_backoff(pol, attempt)
                    continue
                raise T3HTTPError(_format_http_error_message(resp), response=resp)

            if resp.status_code == 204:
                return None
            if not resp.content:
                return None
            try:
                return resp.json()
            except json.JSONDecodeError as e:
                raise T3HTTPError("Failed to decode JSON response.", response=resp) from e
        except httpx.HTTPError as e:
            if _should_retry(policy=pol, attempt=attempt, method=method, exc=e, resp=None):
                await _async_sleep_with_backoff(pol, attempt)
                continue
            raise T3HTTPError(str(e)) from e


# ----------------------
# Token header helpers (no routing)
# ----------------------


def set_bearer_token(*, client: Union[httpx.Client, httpx.AsyncClient], token: str) -> None:
    """Attach or replace the ``Authorization: Bearer`` header on a client.

    Args:
        client: Sync or async ``httpx`` client whose headers will be
            modified in place.
        token: Raw bearer token string (without the ``Bearer `` prefix).
    """
    client.headers["Authorization"] = f"Bearer {token}"


def clear_bearer_token(*, client: Union[httpx.Client, httpx.AsyncClient]) -> None:
    """Remove the ``Authorization`` header from a client, if present.

    Args:
        client: Sync or async ``httpx`` client whose headers will be
            modified in place. No error is raised if the header is
            already absent.
    """
    if "Authorization" in client.headers:
        del client.headers["Authorization"]
