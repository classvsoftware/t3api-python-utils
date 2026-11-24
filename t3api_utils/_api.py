"""Send a request and turn errors into APIError (internal)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import httpx2

from t3api_utils.errors import T3Error, error_from_response


def send(
    http: httpx2.Client,
    method: str,
    url: str,
    *,
    credential_kind: str | None = None,
    **kwargs: Any,
) -> httpx2.Response:
    """Send one request; raise the matching APIError for a non-2xx response."""
    response = http.request(method, url, **kwargs)
    if response.is_error:
        raise error_from_response(response, credential_kind=credential_kind)
    return response


def parse(response: httpx2.Response) -> Any:
    """Parsed JSON for JSON responses, ``None`` for an empty body, else ``bytes``."""
    content = response.content
    if not content:
        return None
    if "json" in response.headers.get("content-type", ""):
        return response.json()
    return content


def require_field(data: Any, field: str, what: str) -> str:
    """Return ``data[field]`` as a string, or raise T3Error if the response lacks it."""
    if isinstance(data, dict) and data.get(field):
        return str(data[field])
    raise T3Error(f"{what} returned an unexpected response (no {field!r}).")


def call(
    http: httpx2.Client,
    method: str,
    url: str,
    *,
    credential_kind: str | None = None,
    **kwargs: Any,
) -> Any:
    return parse(send(http, method, url, credential_kind=credential_kind, **kwargs))


def download(
    http: httpx2.Client,
    url: str,
    target: Path,
    *,
    credential_kind: str | None = None,
    **kwargs: Any,
) -> Path:
    """Stream a GET response to ``target``.

    The body goes to a temporary file next to ``target`` that is renamed only
    once the download finishes, so a failure never leaves a half-written file.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with http.stream("GET", url, **kwargs) as response:
        if response.is_error:
            response.read()
            raise error_from_response(response, credential_kind=credential_kind)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    return target
