"""spec/loader.py: cached copy, live fetch, stale cache, bundled copy."""

from __future__ import annotations

import gzip
import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest

import t3api_utils.spec as spec_pkg
from t3api_utils import _paths
from t3api_utils.errors import SpecError
from t3api_utils.spec import loader
from t3api_utils.spec.loader import SpecSource, bundled_spec, host_key, load_spec
from tests.conftest import Router

BASE = "https://api.test"
T0 = 1_800_000_000.0
SPEC_V1: dict[str, Any] = {"openapi": "3.1.0", "info": {"version": "v1"}, "paths": {"/v2/one": {"get": {}}}}
SPEC_V2: dict[str, Any] = {"openapi": "3.1.0", "info": {"version": "v2"}, "paths": {"/v2/two": {"get": {}}}}


class Clock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def http(router: Router) -> Iterator[httpx2.Client]:
    with httpx2.Client(transport=router.transport) as client:
        yield client


@pytest.fixture
def clock() -> Clock:
    return Clock()


def serve(router: Router, spec: Any = SPEC_V1, *, etag: str = 'W/"v1"', status: int = 200) -> None:
    headers = {"ETag": etag, "Last-Modified": "Mon, 23 Nov 2026 10:00:00 GMT"}
    router.add("GET", loader.SPEC_PATH, json=spec, status=status, headers=headers)


def spec_files(base_url: str = BASE) -> tuple[Path, Path]:
    return loader._cache_files(base_url)


def read_meta(base_url: str = BASE) -> dict[str, Any]:
    meta: dict[str, Any] = json.loads(spec_files(base_url)[1].read_text(encoding="utf-8"))
    return meta


def seed(
    spec: Any = SPEC_V1, *, fetched_at: float | None = T0, etag: str | None = 'W/"v1"', base_url: str = BASE
) -> None:
    meta: dict[str, Any] = {"base_url": base_url}
    if fetched_at is not None:
        meta["fetched_at"] = fetched_at
    if etag is not None:
        meta["etag"] = etag
    assert loader._write_cache(base_url, json.dumps(spec).encode(), meta) is not None


def spec_requests(router: Router) -> list[httpx2.Request]:
    return router.requests("GET", loader.SPEC_PATH)


# --------------------------------------------------------------------------- bundled


def test_bundled_mode_makes_no_request(http: httpx2.Client, router: Router) -> None:
    seed()  # even a fresh cache is ignored
    spec, source = load_spec(http, BASE, "bundled")
    assert spec is bundled_spec()
    assert source == SpecSource(kind="bundled", host="api.test")
    assert router.calls == []


def test_bundled_spec_is_parsed_once_and_looks_like_openapi() -> None:
    spec = bundled_spec()
    assert spec is bundled_spec()
    assert "/v2/items" in spec["paths"]
    assert spec["openapi"].startswith("3.")


# --------------------------------------------------------------------------- live fetch and cache


def test_no_cache_fetches_live_and_writes_cache(http: httpx2.Client, router: Router, clock: Clock) -> None:
    serve(router)
    spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V1
    spec_file, meta_file = spec_files()
    assert source == SpecSource("live", "api.test", spec_file, T0, 'W/"v1"')
    assert spec_file == _paths.cache_dir() / "spec" / "api.test.json.gz"
    assert json.loads(gzip.decompress(spec_file.read_bytes())) == SPEC_V1
    assert read_meta() == {
        "fetched_at": T0,
        "etag": 'W/"v1"',
        "last_modified": "Mon, 23 Nov 2026 10:00:00 GMT",
        "base_url": BASE,
    }
    [request] = spec_requests(router)
    assert str(request.url) == BASE + "/v2/spec/openapi.json"
    assert "If-None-Match" not in request.headers
    assert request.headers["Accept"] == "application/json"
    assert request.extensions["timeout"]["read"] == loader.FETCH_TIMEOUT


def test_trailing_slash_in_base_url(http: httpx2.Client, router: Router) -> None:
    serve(router)
    load_spec(http, BASE + "/")
    assert str(spec_requests(router)[0].url) == BASE + "/v2/spec/openapi.json"


def test_fresh_cache_is_used_without_network(http: httpx2.Client, router: Router, clock: Clock) -> None:
    seed(fetched_at=T0 - 3599)
    spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V1
    assert source == SpecSource("cache", "api.test", spec_files()[0], T0 - 3599, 'W/"v1"')
    assert router.calls == []


def test_stale_cache_revalidates_and_304_refreshes_fetched_at(
    http: httpx2.Client, router: Router, clock: Clock
) -> None:
    seed(fetched_at=T0 - 3600)
    router.add("GET", loader.SPEC_PATH, status=304, content=b"")
    spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V1
    assert source.kind == "cache"
    assert source.fetched_at == T0
    assert source.etag == 'W/"v1"'
    [request] = spec_requests(router)
    assert request.headers["If-None-Match"] == 'W/"v1"'
    assert read_meta()["fetched_at"] == T0
    assert read_meta()["etag"] == 'W/"v1"'

    # Now fresh again: the next load makes no request.
    clock.now += 60
    load_spec(http, BASE, now=clock)
    assert len(spec_requests(router)) == 1


def test_stale_cache_with_new_spec_rewrites_cache(http: httpx2.Client, router: Router, clock: Clock) -> None:
    seed(fetched_at=T0 - 7200)
    serve(router, SPEC_V2, etag='W/"v2"')
    spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V2
    assert source.kind == "live"
    assert source.etag == 'W/"v2"'
    assert json.loads(gzip.decompress(spec_files()[0].read_bytes())) == SPEC_V2
    assert read_meta()["etag"] == 'W/"v2"'
    assert read_meta()["fetched_at"] == T0


def test_cache_without_etag_revalidates_without_if_none_match(
    http: httpx2.Client, router: Router, clock: Clock
) -> None:
    seed(fetched_at=T0 - 7200, etag=None)
    serve(router, SPEC_V2)
    assert load_spec(http, BASE, now=clock)[0] == SPEC_V2
    assert "If-None-Match" not in spec_requests(router)[0].headers


def test_cache_without_fetched_at_counts_as_stale(http: httpx2.Client, router: Router, clock: Clock) -> None:
    seed(fetched_at=None)
    router.add("GET", loader.SPEC_PATH, status=304, content=b"")
    spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V1
    assert source.fetched_at == T0
    assert len(spec_requests(router)) == 1


# --------------------------------------------------------------------------- failures


def raise_connect_error(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("offline", request=request)


FAILURES: dict[str, Callable[[Router], None]] = {
    "connection error": lambda r: r.add("GET", loader.SPEC_PATH, handler=raise_connect_error),
    "server error": lambda r: r.add("GET", loader.SPEC_PATH, status=500, json={"detail": "x"}),
    "not json": lambda r: r.add("GET", loader.SPEC_PATH, content=b"<html>"),
    "not openapi (list)": lambda r: r.add("GET", loader.SPEC_PATH, json=[1, 2]),
    "not openapi (no paths)": lambda r: r.add("GET", loader.SPEC_PATH, json={"openapi": "3.1.0"}),
}


@pytest.mark.parametrize("failure", list(FAILURES))
def test_fetch_failure_falls_back_to_stale_cache(
    failure: str, http: httpx2.Client, router: Router, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    seed(fetched_at=T0 - 7200)
    FAILURES[failure](router)
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V1
    assert source == SpecSource("stale-cache", "api.test", spec_files()[0], T0 - 7200, 'W/"v1"')
    assert "using the cached copy" in caplog.text
    # The stale copy keeps its old timestamp, so the next load tries again.
    assert read_meta()["fetched_at"] == T0 - 7200


@pytest.mark.parametrize("failure", list(FAILURES))
def test_no_cache_and_failure_falls_back_to_bundled(
    failure: str, http: httpx2.Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    FAILURES[failure](router)
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        spec, source = load_spec(http, BASE)
    assert spec is bundled_spec()
    assert source.kind == "bundled"
    assert "using the bundled copy" in caplog.text
    assert not spec_files()[0].exists()


def test_304_without_cache_falls_back_to_bundled(http: httpx2.Client, router: Router) -> None:
    router.add("GET", loader.SPEC_PATH, status=304, content=b"")
    spec, source = load_spec(http, BASE)
    assert spec is bundled_spec()
    assert source.kind == "bundled"


# --------------------------------------------------------------------------- refresh mode


def test_refresh_ignores_fresh_cache(http: httpx2.Client, router: Router, clock: Clock) -> None:
    seed(fetched_at=T0)
    serve(router, SPEC_V2, etag='W/"v2"')
    spec, source = load_spec(http, BASE, "refresh", now=clock)
    assert spec == SPEC_V2
    assert source.kind == "live"
    # A forced refresh is a full fetch, not a revalidation.
    assert "If-None-Match" not in spec_requests(router)[0].headers
    assert read_meta()["etag"] == 'W/"v2"'


@pytest.mark.parametrize("failure", list(FAILURES))
def test_refresh_failure_raises(failure: str, http: httpx2.Client, router: Router) -> None:
    seed(fetched_at=T0 - 7200)
    FAILURES[failure](router)
    with pytest.raises(SpecError, match=r"Couldn't fetch the T3 spec from https://api\.test") as info:
        load_spec(http, BASE, "refresh")
    assert info.value.__cause__ is not None


def test_refresh_with_304_raises(http: httpx2.Client, router: Router) -> None:
    seed()
    router.add("GET", loader.SPEC_PATH, status=304, content=b"")
    with pytest.raises(SpecError, match="returned 304"):
        load_spec(http, BASE, "refresh")


# --------------------------------------------------------------------------- per-host cache


def test_cache_is_keyed_by_host(http: httpx2.Client, router: Router, clock: Clock) -> None:
    serve(router)
    load_spec(http, BASE, now=clock)
    _, source = load_spec(http, "https://sandbox.api.test", now=clock)
    assert source.kind == "live"
    assert source.host == "sandbox.api.test"
    assert [str(r.url.host) for r in spec_requests(router)] == ["api.test", "sandbox.api.test"]
    assert spec_files(BASE)[0] != spec_files("https://sandbox.api.test")[0]
    assert spec_files("https://sandbox.api.test")[0].exists()
    # Both hosts are now served from their own fresh cache.
    load_spec(http, BASE, now=clock)
    load_spec(http, "https://sandbox.api.test", now=clock)
    assert len(spec_requests(router)) == 2


# --------------------------------------------------------------------------- corrupt or unwritable cache


def _corrupt_spec_gzip(spec_file: Path, meta_file: Path) -> None:
    spec_file.write_bytes(b"not gzip at all")


def _truncate_spec_gzip(spec_file: Path, meta_file: Path) -> None:
    spec_file.write_bytes(spec_file.read_bytes()[:-12])


def _spec_not_json(spec_file: Path, meta_file: Path) -> None:
    spec_file.write_bytes(gzip.compress(b"{nope"))


def _spec_without_paths(spec_file: Path, meta_file: Path) -> None:
    spec_file.write_bytes(gzip.compress(b'{"openapi": "3.1.0"}'))


def _spec_not_dict(spec_file: Path, meta_file: Path) -> None:
    spec_file.write_bytes(gzip.compress(b"[1]"))


def _meta_not_json(spec_file: Path, meta_file: Path) -> None:
    meta_file.write_text("{", encoding="utf-8")


def _meta_not_dict(spec_file: Path, meta_file: Path) -> None:
    meta_file.write_text("[]", encoding="utf-8")


def _meta_missing(spec_file: Path, meta_file: Path) -> None:
    meta_file.unlink()


@pytest.mark.parametrize(
    "corrupt",
    [
        _corrupt_spec_gzip,
        _truncate_spec_gzip,
        _spec_not_json,
        _spec_without_paths,
        _spec_not_dict,
        _meta_not_json,
        _meta_not_dict,
        _meta_missing,
    ],
)
def test_unreadable_cache_is_ignored(
    corrupt: Callable[[Path, Path], None], http: httpx2.Client, router: Router, clock: Clock
) -> None:
    seed(fetched_at=T0)  # fresh, but about to be damaged
    corrupt(*spec_files())
    serve(router, SPEC_V2)
    spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V2
    assert source.kind == "live"
    assert "If-None-Match" not in spec_requests(router)[0].headers
    # The damaged cache was replaced.
    assert loader._read_cache(BASE) is not None


def test_unwritable_cache_dir_is_survived(
    http: httpx2.Client,
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setattr(_paths, "cache_dir", lambda: blocker / "cache")
    serve(router)
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        spec, source = load_spec(http, BASE)
    assert spec == SPEC_V1
    assert source.kind == "live"
    assert source.path is None
    assert "Couldn't cache the T3 spec" in caplog.text


def test_failed_write_leaves_no_temp_file(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_replace(src: str, dst: Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", broken_replace)
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert loader._write_cache(BASE, b"{}", {"fetched_at": T0}) is None
    folder = spec_files()[0].parent
    assert list(folder.iterdir()) == []
    assert "locked" in caplog.text


def test_failed_meta_touch_still_uses_cache(
    http: httpx2.Client,
    router: Router,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed(fetched_at=T0 - 7200)
    router.add("GET", loader.SPEC_PATH, status=304, content=b"")

    def read_only(path: Path, data: bytes) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(loader, "_atomic_write", read_only)
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        spec, source = load_spec(http, BASE, now=clock)
    assert spec == SPEC_V1
    assert source.kind == "cache"
    assert source.fetched_at == T0
    assert "Couldn't update the T3 spec cache" in caplog.text
    assert read_meta()["fetched_at"] == T0 - 7200


# --------------------------------------------------------------------------- SpecSource


def test_age_seconds() -> None:
    assert SpecSource("bundled", "h").age_seconds() is None
    source = SpecSource("cache", "h", fetched_at=100.0)
    assert source.age_seconds(now=lambda: 160.0) == 60.0
    # A timestamp from the future never gives a negative age.
    assert source.age_seconds(now=lambda: 50.0) == 0.0
    assert SpecSource("live", "h", fetched_at=time.time()).age_seconds() == pytest.approx(0.0, abs=5)


def test_describe() -> None:
    now = time.time()
    assert SpecSource("bundled", "api.test").describe() == "bundled copy (shipped with t3api-utils)"
    assert SpecSource("live", "api.test", fetched_at=now).describe() == "live copy for api.test, fetched 0s ago"
    assert (
        SpecSource("cache", "api.test", fetched_at=now - 600).describe()
        == "cached copy for api.test, fetched 10m ago"
    )
    assert (
        SpecSource("stale-cache", "api.test", fetched_at=now - 3 * 3600).describe()
        == "stale cached copy for api.test, fetched 3h ago"
    )
    assert SpecSource("cache", "api.test").describe() == "cached copy for api.test"


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0s"),
        (89, "89s"),
        (90, "1m"),
        (5399, "89m"),
        (5400, "1h"),
        (172799, "47h"),
        (172800, "2d"),
        (10 * 86400, "10d"),
    ],
)
def test_human_age(seconds: float, text: str) -> None:
    assert loader._human_age(seconds) == text


# --------------------------------------------------------------------------- host_key


@pytest.mark.parametrize(
    ("base_url", "key"),
    [
        ("https://api.trackandtrace.tools", "api.trackandtrace.tools"),
        ("https://API.Example.COM/", "api.example.com"),
        ("http://localhost:8080", "localhost_8080"),
        ("https://user@host.test", "user_host.test"),
        ("sandbox.example.com", "sandbox.example.com"),
        ("", "default"),
    ],
)
def test_host_key(base_url: str, key: str) -> None:
    assert host_key(base_url) == key


def test_spec_package_exports() -> None:
    assert spec_pkg.load_spec is load_spec
    assert spec_pkg.SpecSource is SpecSource
    assert set(spec_pkg.__all__) == {"Endpoint", "KINDS", "Kind", "Param", "Registry", "SpecSource", "load_spec"}
