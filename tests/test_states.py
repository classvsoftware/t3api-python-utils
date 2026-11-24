from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest

from t3api_utils import _paths
from t3api_utils.auth import states as states_module
from t3api_utils.auth.states import (
    FALLBACK_EMAIL,
    FALLBACK_OTP,
    STATES_PATH,
    STATES_TTL,
    LoginRequirements,
    fetch_states,
    normalize_hostname,
    requirements,
)
from tests.conftest import Router

BASE = "https://api.t3.test"

STATES: list[dict[str, Any]] = [
    {"abbreviation": "CA", "name": "California", "hostname": "ca.metrc.com", "requiresEmail": False, "requiresOtp": False},
    {"abbreviation": "MI", "name": "Michigan", "hostname": "mi.metrc.com", "requiresEmail": False, "requiresOtp": True},
    {"abbreviation": "CO", "name": "Colorado", "hostname": "co.metrc.com", "requiresEmail": True, "requiresOtp": False},
    {"abbreviation": "NV", "name": "Nevada", "hostname": "nv.metrc.com", "requiresEmail": True, "requiresOtp": True},
]


class Clock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def http(router: Router) -> Iterator[httpx2.Client]:
    with httpx2.Client(transport=router.transport) as client:
        yield client


def _cache_file() -> Path:
    return _paths.cache_dir() / "states" / "api.t3.test.json"


def _write_cache(payload: Any) -> None:
    path = _cache_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# --------------------------------------------------------------------------- fetch_states


def test_fetch_states_fetches_and_caches(router: Router, http: httpx2.Client) -> None:
    router.add("GET", STATES_PATH, json=STATES)
    clock = Clock()

    assert fetch_states(http, BASE + "/", now=clock) == STATES

    assert len(router.calls) == 1
    assert str(router.calls[0].url) == BASE + STATES_PATH
    cached = json.loads(_cache_file().read_text(encoding="utf-8"))
    assert cached == {"fetched_at": clock.t, "states": STATES}


def test_fetch_states_uses_cache_for_a_week(router: Router, http: httpx2.Client) -> None:
    router.add("GET", STATES_PATH, json=STATES)
    clock = Clock()
    fetch_states(http, BASE, now=clock)

    clock.t += STATES_TTL - 1
    assert fetch_states(http, BASE, now=clock) == STATES
    assert len(router.calls) == 1


def test_fetch_states_refreshes_when_stale(router: Router, http: httpx2.Client) -> None:
    router.add("GET", STATES_PATH, json=STATES)
    clock = Clock()
    fetch_states(http, BASE, now=clock)

    newer = STATES[:1]
    router.add("GET", STATES_PATH, json=newer)
    clock.t += STATES_TTL
    assert fetch_states(http, BASE, now=clock) == newer
    assert len(router.calls) == 2
    assert json.loads(_cache_file().read_text(encoding="utf-8"))["fetched_at"] == clock.t


def test_fetch_states_refresh_ignores_fresh_cache(router: Router, http: httpx2.Client) -> None:
    _write_cache({"fetched_at": 1_000_000.0, "states": STATES[:1]})
    router.add("GET", STATES_PATH, json=STATES)
    assert fetch_states(http, BASE, now=Clock(), refresh=True) == STATES
    assert len(router.calls) == 1


def test_fetch_states_cache_is_per_host(router: Router, http: httpx2.Client) -> None:
    router.add("GET", STATES_PATH, json=STATES)
    clock = Clock()
    fetch_states(http, BASE, now=clock)
    fetch_states(http, "https://sandbox.t3.test", now=clock)
    fetch_states(http, BASE, now=clock)

    assert [str(r.url) for r in router.calls] == [
        BASE + STATES_PATH,
        "https://sandbox.t3.test" + STATES_PATH,
    ]
    folder = _paths.cache_dir() / "states"
    assert sorted(p.name for p in folder.iterdir()) == ["api.t3.test.json", "sandbox.t3.test.json"]


def test_fetch_states_cache_without_timestamp_is_stale(router: Router, http: httpx2.Client) -> None:
    _write_cache({"states": STATES[:1]})
    router.add("GET", STATES_PATH, json=STATES)
    assert fetch_states(http, BASE, now=Clock()) == STATES


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(500, json={"detail": "down"}),
        httpx2.Response(200, json={"not": "a list"}),
        httpx2.Response(200, content=b"<html>not json</html>"),
    ],
    ids=["server-error", "not-a-list", "not-json"],
)
def test_fetch_states_falls_back_to_stale_cache(
    router: Router, http: httpx2.Client, response: httpx2.Response, caplog: pytest.LogCaptureFixture
) -> None:
    _write_cache({"fetched_at": 0, "states": STATES[:2]})
    router.add("GET", STATES_PATH, handler=lambda request: response)
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        assert fetch_states(http, BASE, now=Clock()) == STATES[:2]
    assert "Couldn't load /v2/states" in caplog.text


def test_fetch_states_no_cache_no_network(router: Router, http: httpx2.Client) -> None:
    def offline(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    router.add("GET", STATES_PATH, handler=offline)
    assert fetch_states(http, BASE, now=Clock()) is None
    assert not _cache_file().exists()


@pytest.mark.parametrize(
    "content",
    ["{broken json", json.dumps(["a list"]), json.dumps({"states": "not a list"})],
    ids=["corrupt", "wrong-type", "states-not-a-list"],
)
def test_fetch_states_ignores_bad_cache(router: Router, http: httpx2.Client, content: str) -> None:
    path = _cache_file()
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    router.add("GET", STATES_PATH, json=STATES)
    assert fetch_states(http, BASE, now=Clock()) == STATES
    assert json.loads(path.read_text(encoding="utf-8"))["states"] == STATES


def test_fetch_states_bad_cache_and_no_network_is_none(router: Router, http: httpx2.Client) -> None:
    _write_cache({"states": None})
    router.add("GET", STATES_PATH, status=503, json={})
    assert fetch_states(http, BASE, now=Clock()) is None


def test_fetch_states_drops_non_dict_rows_everywhere(router: Router, http: httpx2.Client) -> None:
    router.add("GET", STATES_PATH, json=[STATES[0], "junk", 7, None])
    clock = Clock()
    assert fetch_states(http, BASE, now=clock) == [STATES[0]]
    # The cached copy is clean too, so callers can always .get() on each row.
    assert fetch_states(http, BASE, now=clock) == [STATES[0]]
    assert len(router.calls) == 1


def test_fetch_states_survives_cache_write_failure(
    router: Router, http: httpx2.Client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_write(path: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(states_module, "_atomic_write", broken_write)
    router.add("GET", STATES_PATH, json=STATES)
    with caplog.at_level(logging.DEBUG, logger="t3api_utils"):
        assert fetch_states(http, BASE, now=Clock()) == STATES
    assert "disk full" in caplog.text


def test_fetch_states_default_clock(router: Router, http: httpx2.Client) -> None:
    router.add("GET", STATES_PATH, json=STATES)
    assert fetch_states(http, BASE) == STATES
    assert fetch_states(http, BASE) == STATES
    assert len(router.calls) == 1


# --------------------------------------------------------------------------- normalize_hostname


@pytest.mark.parametrize(
    "value",
    ["CA", "ca", "California", "california", " CALIFORNIA ", "https://ca.metrc.com/", "http://CA.metrc.com/login", "ca.metrc.com"],
)
def test_normalize_hostname_with_states(value: str) -> None:
    assert normalize_hostname(value, STATES) == "ca.metrc.com"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CA", "ca.metrc.com"),
        ("ca", "ca.metrc.com"),
        ("https://ca.metrc.com/", "ca.metrc.com"),
        ("ca.metrc.com", "ca.metrc.com"),
        ("California", "california"),  # names need the states list
        ("", ""),
        ("abc", "abc"),
    ],
)
def test_normalize_hostname_without_states(value: str, expected: str) -> None:
    assert normalize_hostname(value) == expected
    assert normalize_hostname(value, []) == expected


def test_normalize_hostname_state_without_hostname() -> None:
    assert normalize_hostname("Narnia", [{"name": "Narnia"}]) == "narnia"
    assert normalize_hostname("XX", [{"abbreviation": "XX", "hostname": "Sandbox-XX.Metrc.com"}]) == "sandbox-xx.metrc.com"


# --------------------------------------------------------------------------- requirements


@pytest.mark.parametrize(
    ("hostname", "email", "otp", "name"),
    [
        ("ca.metrc.com", False, False, "California"),
        ("MI.metrc.com", False, True, "Michigan"),
        ("co.metrc.com", True, False, "Colorado"),
        ("nv.metrc.com", True, True, "Nevada"),
    ],
)
def test_requirements_from_api(hostname: str, email: bool, otp: bool, name: str) -> None:
    assert requirements(hostname, STATES) == LoginRequirements(
        hostname=hostname.lower(), requires_email=email, requires_otp=otp, state_name=name, source="api"
    )


def test_api_data_wins_over_fallback_lists() -> None:
    states: list[dict[str, Any]] = [{"hostname": "mi.metrc.com", "requiresOtp": False}, {"hostname": "co.metrc.com"}]
    assert requirements("mi.metrc.com", states).requires_otp is False
    assert requirements("co.metrc.com", states).requires_email is False
    assert requirements("co.metrc.com", states).state_name is None


@pytest.mark.parametrize("states", [None, [], STATES[:1]])
def test_requirements_fallback(states: list[dict[str, Any]] | None) -> None:
    assert FALLBACK_OTP == {"mi.metrc.com"}
    assert FALLBACK_EMAIL == {"co.metrc.com"}
    mi = requirements("mi.metrc.com", states)
    assert (mi.requires_otp, mi.requires_email, mi.source) == (True, False, "fallback")
    co = requirements("CO.METRC.COM", states)
    assert (co.hostname, co.requires_otp, co.requires_email, co.source) == ("co.metrc.com", False, True, "fallback")
    mo = requirements("mo.metrc.com", states)
    assert (mo.requires_otp, mo.requires_email, mo.state_name) == (False, False, None)
