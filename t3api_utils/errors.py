"""Exceptions raised by t3api-utils.

Every exception the library raises on purpose derives from :class:`T3Error`.
HTTP failures raise an :class:`APIError` subclass that keeps the response.
"""

from __future__ import annotations

import json
from typing import Any

import httpx2

from t3api_utils._http import redact_url

__all__ = [
    "T3Error",
    "AuthRequired",
    "NotInteractive",
    "SpecError",
    "UnknownEndpoint",
    "APIError",
    "AuthError",
    "NotFound",
    "ValidationError",
    "TagListResolveError",
    "RateLimited",
    "ServerError",
    "error_from_response",
]

_MAX_BODY_TEXT = 500


class T3Error(Exception):
    """Base class for every error t3api-utils raises."""


class AuthRequired(T3Error):
    """No credential was found and there is no terminal to ask for one."""


class NotInteractive(T3Error):
    """A prompt or picker was called without a terminal."""


class SpecError(T3Error):
    """The call doesn't fit the endpoint as the OpenAPI spec describes it."""


class UnknownEndpoint(SpecError):
    """An endpoint ID or path isn't in the OpenAPI spec."""

    def __init__(self, name: str, suggestions: list[str] | None = None) -> None:
        self.name = name
        self.suggestions = list(suggestions or [])
        message = f"{name!r} is not in the T3 OpenAPI spec."
        if self.suggestions:
            message += " Close matches: " + ", ".join(self.suggestions) + "."
        message += (
            " Search with client.spec.find(...) or `t3api endpoints`. Routes missing "
            "from the published spec can be reached with client.http."
        )
        super().__init__(message)


class APIError(T3Error):
    """The T3 API answered with a non-2xx status.

    Attributes:
        status_code: The HTTP status code.
        response: The full ``httpx2.Response``.
        method: The request method.
        url: The request URL, with any secret key masked.
        detail: The server's explanation, from a problem+json or error body.
        errors: Per-item errors from a problem+json body, if any.
        code: The server's machine-readable error code, if any.
        hint: What to do about it, when the library knows.
    """

    def __init__(
        self,
        message: str,
        *,
        response: httpx2.Response,
        detail: str | None = None,
        errors: list[Any] | None = None,
        code: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.response = response
        self.status_code = response.status_code
        self.method = response.request.method
        self.url = _safe_url(response.request.url)
        self.detail = detail
        self.errors = list(errors or [])
        self.code = code
        self.hint = hint
        full = message if hint is None else f"{message}\n{hint}"
        super().__init__(full)


class AuthError(APIError):
    """401 or 403: the credential was rejected or lacks access."""


class NotFound(APIError):
    """404."""


class ValidationError(APIError):
    """400 or 422: the server rejected the request as invalid."""


class TagListResolveError(ValidationError):
    """A tag list didn't resolve: some handles matched zero or several objects.

    ``errors`` holds one dict per failing handle, with ``handle``, ``reason``
    (``NOT_FOUND`` or ``AMBIGUOUS``) and ``matchCount``.
    """


class RateLimited(APIError):
    """429, still rate limited after retries."""


class ServerError(APIError):
    """5xx."""


def _safe_url(url: httpx2.URL) -> str:
    return redact_url(str(url))


def _parse_body(response: httpx2.Response) -> tuple[str | None, list[Any], str | None]:
    """Return (detail, errors, code) from an error body, as best it can."""
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        text = response.text.strip()
        if len(text) > _MAX_BODY_TEXT:
            text = text[:_MAX_BODY_TEXT] + "…"
        return (text or None), [], None

    if not isinstance(body, dict):
        return json.dumps(body)[:_MAX_BODY_TEXT], [], None

    errors = body.get("errors")
    error_list = errors if isinstance(errors, list) else []
    code = body.get("code") if isinstance(body.get("code"), str) else None

    # application/problem+json: title, detail, errors, code
    detail = body.get("detail") or body.get("title")
    # T3's older error shape: {"error": {"type": ..., "message": ...}}
    nested = body.get("error")
    if not detail and isinstance(nested, dict):
        detail = nested.get("message") or nested.get("type")
        if code is None and isinstance(nested.get("code"), str):
            code = nested["code"]
    if not detail and isinstance(nested, str):
        detail = nested
    if not detail:
        detail = body.get("message")
    if not detail:
        detail = json.dumps(body)[:_MAX_BODY_TEXT]
    return str(detail), error_list, code


def _auth_hint(status: int, code: str | None, credential_kind: str | None) -> str | None:
    if status == 403:
        return (
            "The credential is valid but doesn't have access to this. Check the "
            "license number and the account's permissions."
        )
    if credential_kind == "secret_key":
        if code == "METRC_LOGIN_FAILURE":
            return (
                "The Metrc credentials behind this secret key have changed. Update the "
                "key with `t3api keys rotate` (the key value stays the same)."
            )
        return (
            "The secret key was rejected: it was deleted or disabled, or the Metrc "
            "credentials behind it changed. Run `t3api keys rotate`, or `t3api login` "
            "to save a new one."
        )
    if credential_kind == "jwt":
        return "The JWT has expired or is invalid (JWTs last 24 hours). Run `t3api login`."
    return "Run `t3api login` to save a credential, or set T3_SECRET_KEY."


def error_from_response(
    response: httpx2.Response, *, credential_kind: str | None = None
) -> APIError:
    """Build the right :class:`APIError` subclass for a non-2xx response.

    The response body must already be read.
    """
    status = response.status_code
    detail, errors, code = _parse_body(response)
    reason = response.reason_phrase or ""
    path = redact_url(response.request.url.path)
    message = f"{status} {reason} from {response.request.method} {path}".replace("  ", " ")
    if detail:
        message += f": {detail}"

    cls: type[APIError]
    hint: str | None = None
    if status in (401, 403):
        cls = AuthError
        hint = _auth_hint(status, code, credential_kind)
    elif status == 404:
        cls = NotFound
    elif status == 422 and (
        code == "TAG_LIST_UNRESOLVED_ENTRIES"
        or (path.startswith("/v2/tag-lists/") and path.endswith("/resolve"))
    ):
        cls = TagListResolveError
    elif status in (400, 422):
        cls = ValidationError
    elif status == 429:
        cls = RateLimited
        hint = "Still rate limited after retries. Lower rate_limit= or concurrency= on connect()."
    elif status >= 500:
        cls = ServerError
    else:
        cls = APIError
    return cls(message, response=response, detail=detail, errors=errors, code=code, hint=hint)
