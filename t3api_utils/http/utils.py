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
    """Base HTTP client configuration (no routes)."""

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


@dataclass(frozen=True)
class LoggingHooks:
    """Optional request/response logging via httpx event hooks."""

    enabled: bool = False

    def as_hooks(self, *, async_client: bool = False) -> Optional[Dict[str, Any]]:
        """Return httpx event_hooks mapping or None."""
        if not self.enabled:
            return None

        async def _alog_request(request: httpx.Request) -> None:
            log.debug("HTTP %s %s", request.method, request.url)

        async def _alog_response(response: httpx.Response) -> None:
            req = response.request
            log.debug("HTTP %s %s -> %s", req.method, req.url, response.status_code)

        def _log_request(request: httpx.Request) -> None:
            log.debug("HTTP %s %s", request.method, request.url)

        def _log_response(response: httpx.Response) -> None:
            req = response.request
            log.debug("HTTP %s %s -> %s", req.method, req.url, response.status_code)

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
        super().__init__(message)
        self.response = response

    @property
    def status_code(self) -> Optional[int]:
        return self.response.status_code if self.response is not None else None


# ----------------------
# Client builders
# ----------------------


def _merge_headers(
    base: Mapping[str, str], extra: Optional[Mapping[str, str]]
) -> Dict[str, str]:
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
    """Construct a configured httpx.Client with sane defaults (no routes)."""
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
    """Construct a configured httpx.AsyncClient with sane defaults (no routes)."""
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
    if attempt <= 1:
        return
    delay = policy.backoff_factor * (2 ** (attempt - 2))
    jitter = delay * 0.2
    time.sleep(max(0.0, delay + random.uniform(-jitter, jitter)))


async def _async_sleep_with_backoff(policy: RetryPolicy, attempt: int) -> None:
    if attempt <= 1:
        return
    delay = policy.backoff_factor * (2 ** (attempt - 2))
    jitter = delay * 0.2
    await asyncio.sleep(max(0.0, delay + random.uniform(-jitter, jitter)))


def _format_http_error_message(resp: httpx.Response) -> str:
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
    headers: Optional[Mapping[str, str]] = None,
    policy: Optional[RetryPolicy] = None,
    expected_status: Union[int, Iterable[int]] = (200, 201, 202, 204),
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    request_id: Optional[str] = None,
) -> Any:
    """Issue a JSON request with retries and return parsed JSON (or None for 204)."""
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
    headers: Optional[Mapping[str, str]] = None,
    policy: Optional[RetryPolicy] = None,
    expected_status: Union[int, Iterable[int]] = (200, 201, 202, 204),
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    request_id: Optional[str] = None,
) -> Any:
    """Async variant of `request_json`. Returns parsed JSON or None for 204."""
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
    """Attach/replace Authorization header in the given client."""
    client.headers["Authorization"] = f"Bearer {token}"


def clear_bearer_token(*, client: Union[httpx.Client, httpx.AsyncClient]) -> None:
    """Remove Authorization header if present."""
    if "Authorization" in client.headers:
        del client.headers["Authorization"]
