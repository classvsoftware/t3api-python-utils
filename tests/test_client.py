"""T3Client: endpoint lookup, path and license filling, parsing, errors, helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest

from t3api_utils import _console
from t3api_utils.auth.credentials import BearerAuth, SecretKeyAuth
from t3api_utils.auth.store import Profile
from t3api_utils.client import T3Client
from t3api_utils.errors import (
    APIError,
    AuthError,
    NotFound,
    RateLimited,
    ServerError,
    SpecError,
    T3Error,
    UnknownEndpoint,
    ValidationError,
)
from t3api_utils.spec.registry import Endpoint, Registry
from tests.conftest import Router, paginated

MINIMAL_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"version": "9.9.9"},
    "paths": {
        "/v2/widgets": {
            "get": {
                "x-t3-endpoint-id": "WIDGETS",
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            }
        }
    },
}


def make_client(router: Router, **kwargs: Any) -> T3Client:
    options: dict[str, Any] = {
        "auth": SecretKeyAuth("test-secret-key"),
        "transport": router.transport,
        "spec": "bundled",
        "rate_limit": None,
    }
    options.update(kwargs)
    return T3Client(**options)


@pytest.fixture
def lic_client(router: Router) -> Iterator[T3Client]:
    """A client whose profile has the default license LIC-1."""
    c = make_client(router, license="LIC-1")
    yield c
    c.close()


# --------------------------------------------------------------------------- construction


def test_concurrency_below_one_raises(router: Router) -> None:
    with pytest.raises(ValueError, match="concurrency"):
        make_client(router, concurrency=0)


def test_base_url_trailing_slash_is_stripped(router: Router) -> None:
    with make_client(router, base_url="https://example.test/") as c:
        assert c.base_url == "https://example.test"


def test_context_manager_closes_the_pool(router: Router) -> None:
    with make_client(router) as c:
        assert not c.http.is_closed
    assert c.http.is_closed


def test_repr_and_credential_kind(router: Router) -> None:
    with make_client(router) as c:
        assert c.credential_kind == "secret_key"
        assert repr(c) == "<T3Client https://api.trackandtrace.tools credential=secret_key>"
    with make_client(router, auth=BearerAuth("a.b.c"), profile=Profile(name="mo")) as c:
        assert c.credential_kind == "jwt"
        assert repr(c) == "<T3Client https://api.trackandtrace.tools credential=jwt profile='mo'>"
    with make_client(router, auth=None) as c:
        assert c.credential_kind is None
        assert "credential=None" in repr(c)


def test_secret_key_property(router: Router) -> None:
    with make_client(router) as c:
        assert c.secret_key == "test-secret-key"
    with make_client(router, auth=BearerAuth("a.b.c")) as c:
        assert c.secret_key is None


def test_secret_keys_and_tag_lists_namespaces(client: T3Client) -> None:
    from t3api_utils.auth.secret_keys import SecretKeys
    from t3api_utils.tag_lists import TagLists

    assert isinstance(client.secret_keys, SecretKeys)
    assert isinstance(client.tag_lists, TagLists)


# --------------------------------------------------------------------------- spec


def test_spec_loads_lazily_and_once(router: Router) -> None:
    router.add("GET", "/v2/spec/openapi.json", json=MINIMAL_SPEC)
    with make_client(router, spec="auto") as c:
        assert router.calls == []
        first = c.spec
        second = c.spec
        assert first is second
        assert len(router.requests("GET", "/v2/spec/openapi.json")) == 1
        assert first.source is not None and first.source.kind == "live"
        assert [ep.id for ep in first.endpoints] == ["WIDGETS"]


def test_spec_bundled_mode_sends_no_request(client: T3Client, router: Router) -> None:
    assert client.spec.source is not None and client.spec.source.kind == "bundled"
    assert router.calls == []


def test_spec_uses_registry_set_by_a_racing_thread(
    client: T3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Double-checked locking: if another thread loaded the spec while this one
    waited for the lock, its registry is used and nothing is loaded again."""
    winner = Registry(MINIMAL_SPEC)

    class RacingLock:
        def __enter__(self) -> RacingLock:
            client._registry = winner
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("load_spec should not be called")

    monkeypatch.setattr("t3api_utils.client.load_spec", fail)
    monkeypatch.setattr(client, "_spec_lock", RacingLock())
    assert client.spec is winner


def test_refresh_spec_fetches_live_copy(client: T3Client, router: Router) -> None:
    bundled = client.spec
    router.add("GET", "/v2/spec/openapi.json", json=MINIMAL_SPEC)
    refreshed = client.refresh_spec()
    assert refreshed is not bundled
    assert client.spec is refreshed
    assert refreshed.version == "9.9.9"
    assert refreshed.source is not None and refreshed.source.kind == "live"
    assert len(router.requests("GET", "/v2/spec/openapi.json")) == 1


# --------------------------------------------------------------------------- request / get


def test_get_by_id_picks_collection_route(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", json={"data": [], "totalPages": 1})
    assert lic_client.get("METRC_ACTIVE_ITEMS") == {"data": [], "totalPages": 1}
    (request,) = router.calls
    assert request.method == "GET"
    assert request.url.path == "/v2/items"
    assert request.url.params["licenseNumber"] == "LIC-1"


def test_get_by_id_with_object_id_picks_object_route(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/{object_id}", json={"id": 5, "name": "Widget"})
    assert lic_client.get("METRC_ACTIVE_ITEMS", object_id=5) == {"id": 5, "name": "Widget"}
    (request,) = router.calls
    assert request.url.path == "/v2/items/5"


def test_get_concrete_path(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/{object_id}", json={"id": 5})
    assert lic_client.get("/v2/items/5") == {"id": 5}
    assert router.calls[0].url.path == "/v2/items/5"


def test_get_concrete_path_with_trailing_slash(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", json=[])
    lic_client.get("/v2/items/")
    assert router.calls[0].url.path == "/v2/items"


def test_get_template_path_with_keyword(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/{object_id}", json={"id": 7})
    assert lic_client.get("/v2/items/{object_id}", object_id=7) == {"id": 7}
    assert router.calls[0].url.path == "/v2/items/7"


def test_path_values_are_url_encoded(lic_client: T3Client, router: Router) -> None:
    # The decoded path contains a slash, so route it literally.
    router.add("GET", "/v2/items/a/b c?", json={"ok": True})
    assert lic_client.get("METRC_ACTIVE_ITEMS", object_id="a/b c?") == {"ok": True}
    assert router.calls[0].url.raw_path.startswith(b"/v2/items/a%2Fb%20c%3F?")


def test_unknown_path_keyword_raises_type_error(lic_client: T3Client, router: Router) -> None:
    with pytest.raises(TypeError, match="no path parameter"):
        lic_client.get("METRC_ACTIVE_ITEMS", bogus=1)
    assert router.calls == []


def test_concrete_path_with_path_keyword_raises(lic_client: T3Client, router: Router) -> None:
    with pytest.raises(TypeError, match="already contains"):
        lic_client.get("/v2/items/5", object_id=5)
    assert router.calls == []


@pytest.mark.parametrize("value", [None, ""])
def test_empty_path_value_raises_spec_error(lic_client: T3Client, router: Router, value: Any) -> None:
    with pytest.raises(SpecError, match="object_id="):
        lic_client.get("METRC_ACTIVE_ITEMS", object_id=value)
    assert router.calls == []


def test_template_path_without_value_raises_spec_error(lic_client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="object_id="):
        lic_client.get("/v2/items/{object_id}")
    assert router.calls == []


def test_query_string_in_endpoint_is_rejected(lic_client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="params="):
        lic_client.get("/v2/items?filter=name__eq:x")
    with pytest.raises(ValueError, match="params="):
        lic_client.collect("/v2/items?filter=name__eq:x")
    assert router.calls == []


def test_unknown_endpoint(client: T3Client, router: Router) -> None:
    with pytest.raises(UnknownEndpoint):
        client.get("METRC_NOPE_ITEMS")
    assert router.calls == []


def test_missing_required_license_raises_before_sending(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="license="):
        client.get("METRC_ACTIVE_ITEMS")
    assert router.calls == []


def test_missing_required_body_raises_before_sending(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="request body"):
        client.post("/v2/items/discontinue", license="LIC-1")
    assert router.calls == []


def test_explicit_license_wins_over_default(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/{object_id}", json={})
    lic_client.get("METRC_ACTIVE_ITEMS", object_id=1, license="LIC-2")
    assert router.calls[0].url.params.get_list("licenseNumber") == ["LIC-2"]


def test_default_license_only_fills_required_license(lic_client: T3Client, router: Router) -> None:
    # /v2/saved-reports takes licenseNumber but doesn't require it.
    router.add("GET", "/v2/saved-reports", json={"data": [], "totalPages": 1})
    # /v2/auth/whoami takes no licenseNumber at all.
    router.add("GET", "/v2/auth/whoami", json={"username": "jdoe"})
    lic_client.get("/v2/saved-reports")
    lic_client.get("/v2/auth/whoami")
    assert all("licenseNumber" not in r.url.params for r in router.calls)


def test_default_license_is_a_list_for_array_params(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/report", content=b"a,b\n", headers={"content-type": "text/csv"})
    assert lic_client.request("GET", "ITEMS_REPORT") == b"a,b\n"
    assert router.calls[0].url.params.get_list("licenseNumber") == ["LIC-1"]


def test_params_are_passed_through(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/{object_id}", json={})
    lic_client.get("METRC_ACTIVE_ITEMS", object_id=1, params={"collectionMask": "id,name"})
    assert router.calls[0].url.params["collectionMask"] == "id,name"


def test_unknown_query_parameter_warns_and_sends(
    lic_client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("GET", "/v2/items/{object_id}", json={})
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        lic_client.get("METRC_ACTIVE_ITEMS", object_id=1, params={"brandNew": "x"})
    assert router.calls[0].url.params["brandNew"] == "x"
    assert "brandNew" in caplog.text


def test_timeout_is_passed_to_the_request(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items/{object_id}", json={})
    lic_client.get("METRC_ACTIVE_ITEMS", object_id=1, timeout=7.5)
    assert router.calls[0].extensions["timeout"]["read"] == 7.5


def test_secret_key_is_sent_in_header_only(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", json={})
    client.get("/v2/auth/whoami")
    request = router.calls[0]
    assert request.headers["X-T3-API-Key"] == "test-secret-key"
    assert "secretKey" not in request.url.params


# --------------------------------------------------------------------------- parsing


def test_json_response_is_parsed(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", json={"username": "jdoe"})
    assert client.get("/v2/auth/whoami") == {"username": "jdoe"}


def test_non_json_response_is_bytes(client: T3Client, router: Router) -> None:
    router.add(
        "GET", "/v2/transfers/manifest", content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
    )
    body = client.get("/v2/transfers/manifest", license="LIC-1", params={"manifestNumber": "0001"})
    assert body == b"%PDF-1.7"


def test_empty_response_is_none(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", status=204, content=b"")
    assert client.get("/v2/auth/whoami") is None


# --------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, ValidationError),
        (401, AuthError),
        (403, AuthError),
        (404, NotFound),
        (409, APIError),
        (422, ValidationError),
        (429, RateLimited),
        (500, ServerError),
        (503, ServerError),
    ],
)
def test_non_2xx_raises_matching_error(
    client: T3Client, router: Router, sleeps: list[float], status: int, error: type[APIError]
) -> None:
    router.add("GET", "/v2/auth/whoami", status=status, json={"detail": f"boom {status}"})
    with pytest.raises(error) as info:
        client.get("/v2/auth/whoami")
    exc = info.value
    assert type(exc) is error
    assert exc.status_code == status
    assert exc.response.status_code == status
    assert exc.detail == f"boom {status}"
    assert exc.method == "GET"
    retried = status in (429, 503)
    assert len(router.calls) == (3 if retried else 1)
    assert len(sleeps) == (2 if retried else 0)


def test_auth_error_hint_names_the_secret_key(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", status=401, json={"detail": "nope"})
    with pytest.raises(AuthError) as info:
        client.whoami()
    assert info.value.hint is not None and "t3api keys rotate" in info.value.hint


def test_auth_error_hint_for_jwt(router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", status=401, json={"detail": "expired"})
    with make_client(router, auth=BearerAuth("a.b.c")) as c, pytest.raises(AuthError) as info:
        c.whoami()
    assert info.value.hint is not None and "t3api login" in info.value.hint


# --------------------------------------------------------------------------- helpers


def test_whoami(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", json={"username": "jdoe"})
    assert client.whoami() == {"username": "jdoe"}
    router.add("GET", "/v2/auth/whoami", json=["unexpected"])
    assert client.whoami() == {}


def test_licenses(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/licenses", json=[{"licenseNumber": "LIC-1"}])
    assert client.licenses() == [{"licenseNumber": "LIC-1"}]
    router.add("GET", "/v2/licenses", json={"unexpected": True})
    assert client.licenses() == []


def test_states(client: T3Client, router: Router) -> None:
    states = [{"hostname": "ca.metrc.com", "requiresEmail": False, "requiresOtp": False}]
    router.add("GET", "/v2/states", json=states)
    assert client.states() == states


def test_states_unavailable_is_empty(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/states", status=500, json={})
    assert client.states() == []


def test_enter_sandbox_swaps_credential(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/auth/sandbox", json={"accessToken": "sandbox-jwt"})
    router.add("GET", "/v2/auth/whoami", json={})
    client.enter_sandbox()
    assert client.credential_kind == "jwt"
    assert client.secret_key is None
    client.whoami()
    request = router.requests("GET", "/v2/auth/whoami")[0]
    assert request.headers["Authorization"] == "Bearer sandbox-jwt"
    assert "X-T3-API-Key" not in request.headers


def test_pick_license_with_one_license(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/licenses", json=[{"licenseNumber": "LIC-9", "licenseName": "Only"}])
    assert client.pick_license() == "LIC-9"


def test_pick_endpoint_offers_endpoints_of_the_kind(
    client: T3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    offered: list[list[Endpoint]] = []

    def fake_pick(endpoints: list[Endpoint]) -> Endpoint:
        offered.append(list(endpoints))
        return endpoints[0]

    monkeypatch.setattr("t3api_utils.pickers.pick_endpoint", fake_pick)
    chosen = client.pick_endpoint()
    assert chosen.kind == "collection"
    assert offered[0] and all(ep.kind == "collection" for ep in offered[0])
    client.pick_endpoint(kind=None)
    assert len(offered[1]) == len(client.spec.endpoints)


def test_pick_endpoint_needs_a_terminal(client: T3Client) -> None:
    from t3api_utils.errors import NotInteractive

    assert not _console.is_interactive()
    with pytest.raises(NotInteractive):
        client.pick_endpoint("report")


def test_http_escape_hatch_is_configured(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/anything-new", json={"ok": 1})
    assert client.http.get("/v2/anything-new").json() == {"ok": 1}
    request = router.calls[0]
    assert request.headers["X-T3-API-Key"] == "test-secret-key"
    assert request.headers["User-Agent"].startswith("t3api-utils/")


def test_enter_sandbox_with_unexpected_body_raises_t3error(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/auth/sandbox", json={"unexpected": True})
    with pytest.raises(T3Error, match="no 'accessToken'"):
        client.enter_sandbox()
    assert client.credential_kind == "secret_key"


# --------------------------------------------------------------------------- include= on get()


def test_get_object_with_include(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/packages/active/super/{object_id}", json={"id": 7})
    assert lic_client.get("METRC_ACTIVE_SUPERPACKAGES", object_id=7, include=["history", "labResults"]) == {"id": 7}
    assert router.calls[0].url.params.get_list("include") == ["history", "labResults"]


# --------------------------------------------------------------------------- download()

MANIFEST = "/v2/transfers/manifest"


def test_download_streams_a_file_to_disk(lic_client: T3Client, router: Router, tmp_path: Path) -> None:
    router.add("GET", MANIFEST, content=b"%PDF-1.7 manifest", headers={"content-type": "application/pdf"})
    target = tmp_path / "manifests" / "0001.pdf"
    path = lic_client.download(MANIFEST, target, params={"manifestNumber": "0001"})
    assert path == target
    assert target.read_bytes() == b"%PDF-1.7 manifest"
    assert [p.name for p in target.parent.iterdir()] == ["0001.pdf"]
    request = router.calls[0]
    assert request.url.params["licenseNumber"] == "LIC-1"
    assert request.url.params["manifestNumber"] == "0001"


def test_download_fills_path_parameters_and_accepts_a_string(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/coa/{public_id}.pdf", content=b"%PDF coa")
    path = client.download("/v2/coa/{public_id}.pdf", "coa.pdf", public_id="abc 1")
    assert path.read_bytes() == b"%PDF coa"
    assert router.calls[0].url.raw_path == b"/v2/coa/abc%201.pdf"


def test_download_error_leaves_no_file(lic_client: T3Client, router: Router, tmp_path: Path) -> None:
    router.add("GET", MANIFEST, status=404, json={"detail": "no such manifest"})
    folder = tmp_path / "out"
    with pytest.raises(NotFound, match="no such manifest"):
        lic_client.download(MANIFEST, folder / "missing.pdf", params={"manifestNumber": "9"})
    assert list(folder.iterdir()) == []


def test_download_interrupted_leaves_no_partial_file(
    lic_client: T3Client, router: Router, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    router.add("GET", MANIFEST, content=b"%PDF")

    def broken_replace(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("t3api_utils._api.os.replace", broken_replace)
    folder = tmp_path / "out"
    with pytest.raises(OSError, match="disk full"):
        lic_client.download(MANIFEST, folder / "m.pdf", params={"manifestNumber": "1"})
    assert list(folder.iterdir()) == []


def test_download_passes_a_timeout(lic_client: T3Client, router: Router, tmp_path: Path) -> None:
    seen: list[Any] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.extensions["timeout"])
        return httpx2.Response(200, content=b"x")

    router.add("GET", MANIFEST, handler=handler)
    lic_client.download(MANIFEST, tmp_path / "a.pdf", params={"manifestNumber": "1"})
    lic_client.download(MANIFEST, tmp_path / "b.pdf", params={"manifestNumber": "1"}, timeout=120)
    assert seen[0]["read"] != 120
    assert seen[1]["read"] == 120


def test_download_rejects_endpoints_that_are_not_files(lic_client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="file"):
        lic_client.download("METRC_ACTIVE_ITEMS", "items.json")
    assert router.calls == []


def test_download_checks_required_parameters(lic_client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="manifestNumber"):
        lic_client.download(MANIFEST, "m.pdf")
    assert router.calls == []


# --------------------------------------------------------------------------- sandbox

SANDBOX_LICENSES = [{"licenseNumber": "SF-SBX-1-101"}, {"licenseNumber": "SF-SBX-2-101"}]


@pytest.fixture
def sandbox_api(router: Router) -> Router:
    router.add("POST", "/v2/auth/sandbox", json={"accessToken": "sandbox-jwt"})
    router.add("GET", "/v2/auth/whoami", json={"hostname": "sandbox-me.metrc.com"})
    router.add("GET", "/v2/licenses", json=SANDBOX_LICENSES)
    router.add("GET", "/v2/items", handler=paginated([]))
    return router


def test_enter_sandbox_clears_the_default_license_and_logs(
    sandbox_api: Router, caplog: pytest.LogCaptureFixture
) -> None:
    with make_client(sandbox_api, license="AR1769") as c, caplog.at_level(logging.INFO, logger="t3api_utils"):
        before = c.sandbox
        c.enter_sandbox()
        assert (before, c.sandbox) == (False, True)
        assert c.license is None
        assert c.hostname == "sandbox-me.metrc.com"
        assert repr(c).endswith("credential=jwt sandbox>")
    assert "Using the Metrc sandbox (sandbox-me.metrc.com)." in caplog.text
    assert len(sandbox_api.requests("GET", "/v2/auth/whoami")) == 1


def test_enter_sandbox_with_no_hostname(router: Router, caplog: pytest.LogCaptureFixture) -> None:
    router.add("POST", "/v2/auth/sandbox", json={"accessToken": "sandbox-jwt"})
    router.add("GET", "/v2/auth/whoami", json=["not", "a", "dict"])
    with make_client(router) as c, caplog.at_level(logging.INFO, logger="t3api_utils"):
        c.enter_sandbox()
        assert c.hostname is None
    assert "Using the Metrc sandbox (unknown host)." in caplog.text


def test_hostname_calls_whoami_once(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/auth/whoami", json={"hostname": "ca.metrc.com"})
    assert client.hostname == "ca.metrc.com"
    assert client.hostname == "ca.metrc.com"
    assert len(router.calls) == 1


def test_sandbox_warns_once_about_a_license_it_does_not_have(
    sandbox_api: Router, caplog: pytest.LogCaptureFixture
) -> None:
    with make_client(sandbox_api) as c:
        c.enter_sandbox()
        c.collect("METRC_ACTIVE_ITEMS", license="AR1769", progress=False)
        c.collect("METRC_ACTIVE_ITEMS", license=["AR1769", "SF-SBX-1-101"], progress=False)
    warnings = [r.getMessage() for r in caplog.records if "isn't one of this sandbox" in r.getMessage()]
    assert warnings == [
        "AR1769 isn't one of this sandbox session's licenses (SF-SBX-1-101, SF-SBX-2-101). The sandbox "
        "answers requests for other licenses with no rows instead of an error."
    ]
    assert len(sandbox_api.requests("GET", "/v2/licenses")) == 1


def test_sandbox_checks_licenses_on_writes(sandbox_api: Router, caplog: pytest.LogCaptureFixture) -> None:
    sandbox_api.add("POST", "/v2/items/discontinue", json={"message": "Dry run"})
    with make_client(sandbox_api) as c:
        c.enter_sandbox()
        c.post("/v2/items/discontinue", license="SF-SBX-1-101", json={"id": 1})
        assert "isn't one of" not in caplog.text
        c.post("/v2/items/discontinue", license="LIC-PROD", json={"id": 1})
    assert "LIC-PROD isn't one of this sandbox session's licenses" in caplog.text


def test_sandbox_license_check_skipped_when_licenses_fail(
    sandbox_api: Router, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox_api.add("GET", "/v2/licenses", status=403, json={"detail": "nope"})
    with make_client(sandbox_api) as c, caplog.at_level(logging.DEBUG, logger="t3api_utils"):
        c.enter_sandbox()
        c.collect("METRC_ACTIVE_ITEMS", license="AR1769", progress=False)
        c.collect("METRC_ACTIVE_ITEMS", license="AR1769", progress=False)
    assert "Couldn't list the sandbox licenses to check AR1769" in caplog.text
    assert "isn't one of" not in caplog.text
    assert len(sandbox_api.requests("GET", "/v2/licenses")) == 1


def test_no_license_check_outside_the_sandbox(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated([]))
    lic_client.collect("METRC_ACTIVE_ITEMS", license="ANYTHING", progress=False)
    assert router.requests("GET", "/v2/licenses") == []
