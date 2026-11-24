"""_api.py: send(), parse() and call()."""

from __future__ import annotations

from collections.abc import Iterator

import httpx2
import pytest

from t3api_utils import _api
from t3api_utils.errors import AuthError, NotFound, ServerError
from tests.conftest import Router


@pytest.fixture
def http(router: Router) -> Iterator[httpx2.Client]:
    with httpx2.Client(base_url="https://api.test", transport=router.transport) as client:
        yield client


def test_send_returns_successful_response(http: httpx2.Client, router: Router) -> None:
    router.add("GET", "/v2/licenses", json=[{"licenseNumber": "L1"}])
    response = _api.send(http, "GET", "/v2/licenses", params={"a": "1"})
    assert response.status_code == 200
    assert router.calls[0].url.params["a"] == "1"


def test_send_raises_matching_error(http: httpx2.Client, router: Router) -> None:
    router.add("GET", "/v2/items/{id}", status=404, json={"detail": "gone"})
    with pytest.raises(NotFound) as info:
        _api.send(http, "GET", "/v2/items/9")
    assert info.value.detail == "gone"
    assert info.value.response.status_code == 404


def test_send_passes_credential_kind(http: httpx2.Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", status=401, json={"detail": "expired"})
    with pytest.raises(AuthError) as info:
        _api.send(http, "GET", "/v2/auth/whoami", credential_kind="jwt")
    assert info.value.hint is not None and "JWT" in info.value.hint


def test_parse_json() -> None:
    response = httpx2.Response(200, json={"a": 1})
    assert _api.parse(response) == {"a": 1}


def test_parse_problem_json_content_type() -> None:
    response = httpx2.Response(
        200, content=b'{"b": 2}', headers={"content-type": "application/problem+json"}
    )
    assert _api.parse(response) == {"b": 2}


def test_parse_empty_body_is_none() -> None:
    assert _api.parse(httpx2.Response(204)) is None
    assert _api.parse(httpx2.Response(200, content=b"", headers={"content-type": "application/json"})) is None


def test_parse_non_json_is_bytes() -> None:
    response = httpx2.Response(200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv"})
    assert _api.parse(response) == b"a,b\n1,2\n"
    no_type = httpx2.Response(200, content=b"\x89PNG")
    assert _api.parse(no_type) == b"\x89PNG"


def test_call_parses(http: httpx2.Client, router: Router) -> None:
    router.add("POST", "/v2/things", json={"ok": True})
    assert _api.call(http, "POST", "/v2/things", json={"x": 1}) == {"ok": True}
    assert router.calls[0].content == b'{"x":1}'


def test_call_raises(http: httpx2.Client, router: Router) -> None:
    router.add("GET", "/v2/boom", status=500, content=b"oops")
    with pytest.raises(ServerError):
        _api.call(http, "GET", "/v2/boom", credential_kind="secret_key")
