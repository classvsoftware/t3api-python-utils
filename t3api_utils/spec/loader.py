"""Finds the OpenAPI spec: a cached live copy, a fresh fetch, or the bundled copy.

Order (section 5 of the design):

1. The cached live copy, if it is less than an hour old. Once older, it is
   revalidated with ``If-None-Match``; an unchanged spec costs a 304.
2. A live fetch from ``<base URL>/v2/spec/openapi.json`` (5 second timeout).
3. The stale cache, if the fetch fails.
4. The bundled copy that ships in the package.
"""

from __future__ import annotations

import functools
import gzip
import json
import logging
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx2

from t3api_utils import _paths
from t3api_utils.errors import SpecError

logger = logging.getLogger("t3api_utils")

SPEC_PATH = "/v2/spec/openapi.json"
REVALIDATE_AFTER = 3600.0
FETCH_TIMEOUT = 5.0

SpecMode = Literal["auto", "bundled", "refresh"]
SourceKind = Literal["bundled", "cache", "live", "stale-cache"]


@dataclass(frozen=True)
class SpecSource:
    """Which copy of the spec is in use."""

    kind: SourceKind
    host: str
    path: Path | None = None
    fetched_at: float | None = None
    etag: str | None = None

    def age_seconds(self, now: Callable[[], float] = time.time) -> float | None:
        if self.fetched_at is None:
            return None
        return max(0.0, now() - self.fetched_at)

    def describe(self) -> str:
        if self.kind == "bundled":
            return "bundled copy (shipped with t3api-utils)"
        age = self.age_seconds()
        when = "" if age is None else f", fetched {_human_age(age)} ago"
        label = {"cache": "cached copy", "live": "live copy", "stale-cache": "stale cached copy"}
        return f"{label[self.kind]} for {self.host}{when}"


def _human_age(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 5400:
        return f"{int(seconds // 60)}m"
    if seconds < 172800:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def host_key(base_url: str) -> str:
    """A file-name-safe key for an API host, e.g. ``api.trackandtrace.tools``."""
    netloc = urlsplit(base_url).netloc or base_url
    return re.sub(r"[^A-Za-z0-9.-]+", "_", netloc.lower()) or "default"


@functools.cache
def bundled_spec() -> dict[str, Any]:
    """The spec that ships in the package (parsed once per process; don't mutate it)."""
    data = resources.files("t3api_utils.spec").joinpath("openapi.json.gz").read_bytes()
    spec: dict[str, Any] = json.loads(gzip.decompress(data))
    return spec


def _cache_files(base_url: str) -> tuple[Path, Path]:
    folder = _paths.cache_dir() / "spec"
    key = host_key(base_url)
    return folder / f"{key}.json.gz", folder / f"{key}.meta.json"


def _read_cache(base_url: str) -> tuple[dict[str, Any], dict[str, Any], Path] | None:
    spec_file, meta_file = _cache_files(base_url)
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        spec = json.loads(gzip.decompress(spec_file.read_bytes()))
    except (OSError, ValueError, EOFError):
        return None
    if not isinstance(spec, dict) or "paths" not in spec or not isinstance(meta, dict):
        return None
    return spec, meta, spec_file


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _write_cache(base_url: str, raw: bytes, meta: dict[str, Any]) -> Path | None:
    spec_file, meta_file = _cache_files(base_url)
    try:
        _atomic_write(spec_file, gzip.compress(raw))
        _atomic_write(meta_file, json.dumps(meta).encode())
    except OSError as exc:
        logger.warning("Couldn't cache the T3 spec in %s: %s", spec_file.parent, exc)
        return None
    return spec_file


def _touch_meta(base_url: str, meta: dict[str, Any]) -> None:
    _, meta_file = _cache_files(base_url)
    try:
        _atomic_write(meta_file, json.dumps(meta).encode())
    except OSError as exc:
        logger.warning("Couldn't update the T3 spec cache: %s", exc)


def _fetch(
    http: httpx2.Client, base_url: str, etag: str | None
) -> tuple[int, bytes, dict[str, str]]:
    headers = {"Accept": "application/json"}
    if etag:
        headers["If-None-Match"] = etag
    url = base_url.rstrip("/") + SPEC_PATH
    response = http.get(url, headers=headers, timeout=FETCH_TIMEOUT)
    return response.status_code, response.content, dict(response.headers)


def load_spec(
    http: httpx2.Client,
    base_url: str,
    mode: SpecMode = "auto",
    *,
    now: Callable[[], float] = time.time,
) -> tuple[dict[str, Any], SpecSource]:
    """Return ``(spec, source)``.

    ``mode="bundled"`` pins the bundled copy. ``mode="refresh"`` forces a full
    fetch and raises :class:`SpecError` if it fails.
    """
    host = host_key(base_url)
    if mode == "bundled":
        return bundled_spec(), SpecSource(kind="bundled", host=host)

    cached = None if mode == "refresh" else _read_cache(base_url)
    if cached is not None:
        spec, meta, path = cached
        fetched_at = float(meta.get("fetched_at", 0))
        if now() - fetched_at < REVALIDATE_AFTER:
            return spec, SpecSource("cache", host, path, fetched_at, meta.get("etag"))

    etag = cached[1].get("etag") if cached is not None else None
    try:
        status, raw, headers = _fetch(http, base_url, etag)
        if status == 304 and cached is not None:
            spec, meta, path = cached
            meta = {**meta, "fetched_at": now()}
            _touch_meta(base_url, meta)
            return spec, SpecSource("cache", host, path, meta["fetched_at"], meta.get("etag"))
        if status != 200:
            raise SpecError(f"GET {SPEC_PATH} returned {status}")
        spec = json.loads(raw)
        if not isinstance(spec, dict) or "paths" not in spec:
            raise SpecError(f"GET {SPEC_PATH} didn't return an OpenAPI document")
    except (httpx2.HTTPError, ValueError, SpecError) as exc:
        if mode == "refresh":
            raise SpecError(f"Couldn't fetch the T3 spec from {base_url}: {exc}") from exc
        if cached is not None:
            spec, meta, path = cached
            logger.warning("Couldn't refresh the T3 spec (%s); using the cached copy.", exc)
            return spec, SpecSource(
                "stale-cache", host, path, float(meta.get("fetched_at", 0)), meta.get("etag")
            )
        logger.info("Couldn't fetch the T3 spec (%s); using the bundled copy.", exc)
        return bundled_spec(), SpecSource(kind="bundled", host=host)

    lowered = {k.lower(): v for k, v in headers.items()}
    meta = {
        "fetched_at": now(),
        "etag": lowered.get("etag"),
        "last_modified": lowered.get("last-modified"),
        "base_url": base_url,
    }
    written = _write_cache(base_url, raw, meta)
    return spec, SpecSource("live", host, written, meta["fetched_at"], meta["etag"])
