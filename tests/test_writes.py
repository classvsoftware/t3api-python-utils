"""post/put/patch/delete: dry runs, submit, immediate routes, WriteResult."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx2
import pytest

from t3api_utils.client import T3Client
from t3api_utils.errors import ServerError, SpecError, ValidationError
from t3api_utils.writes import WriteResult
from tests.conftest import Router

DISCONTINUE = "/v2/items/discontinue"


def body_of(request: httpx2.Request) -> Any:
    return json.loads(request.content)


# --------------------------------------------------------------------------- metrc_write routes


def test_metrc_write_is_a_dry_run_by_default(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("POST", DISCONTINUE, json={"message": "Dry run", "data": {"id": 1}})
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        result = client.post(DISCONTINUE, license="LIC-1", json={"id": 1})
    assert isinstance(result, WriteResult)
    assert result.dry_run is True
    assert result.message == "Dry run"
    assert result.data == {"message": "Dry run", "data": {"id": 1}}
    assert result.response.status_code == 200
    (request,) = router.calls
    assert "submit" not in request.url.params
    assert request.url.params["licenseNumber"] == "LIC-1"
    assert body_of(request) == {"id": 1}
    assert "dry run: pass submit=True to send POST /v2/items/discontinue to Metrc" in caplog.text


def test_metrc_write_submit_true_sends_submit(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("POST", DISCONTINUE, json={"message": "Success"})
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        result = client.post(DISCONTINUE, license="LIC-1", json={"id": 1}, submit=True)
    assert result.dry_run is False
    assert result.message == "Success"
    assert router.calls[0].url.params["submit"] == "true"
    assert "dry run" not in caplog.text


def test_metrc_write_submit_false_is_a_dry_run(client: T3Client, router: Router) -> None:
    router.add("POST", DISCONTINUE, json={"message": "Dry run"})
    result = client.post(DISCONTINUE, license="LIC-1", json={"id": 1}, submit=False)
    assert result.dry_run is True
    assert "submit" not in router.calls[0].url.params


def test_write_result_repr_hides_response(client: T3Client, router: Router) -> None:
    router.add("POST", DISCONTINUE, json={"message": "Dry run"})
    result = client.post(DISCONTINUE, license="LIC-1", json={"id": 1})
    assert "response" not in repr(result)
    assert "Dry run" in repr(result)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"[1, 2]", id="list"),
        pytest.param(b'{"message": {"not": "a string"}}', id="non-string message"),
    ],
)
def test_message_is_none_unless_a_string(client: T3Client, router: Router, body: bytes) -> None:
    router.add("POST", DISCONTINUE, content=body, headers={"content-type": "application/json"})
    result = client.post(DISCONTINUE, license="LIC-1", json={"id": 1})
    assert result.message is None
    assert result.data == (json.loads(body) if body else None)


def test_write_uses_the_default_license(router: Router) -> None:
    from t3api_utils.auth.credentials import SecretKeyAuth

    router.add("POST", DISCONTINUE, json={"message": "Dry run"})
    with T3Client(
        auth=SecretKeyAuth("k"), license="LIC-5", transport=router.transport, spec="bundled", rate_limit=None
    ) as c:
        c.post(DISCONTINUE, json={"id": 1})
    assert router.calls[0].url.params["licenseNumber"] == "LIC-5"


def test_write_missing_license_raises_before_sending(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="license="):
        client.post(DISCONTINUE, json={"id": 1})
    assert router.calls == []


def test_write_validation_error_keeps_response(client: T3Client, router: Router) -> None:
    router.add(
        "POST",
        DISCONTINUE,
        status=400,
        json={"detail": "Item 1 not found", "errors": [{"id": 1}]},
        headers={"content-type": "application/problem+json"},
    )
    with pytest.raises(ValidationError) as info:
        client.post(DISCONTINUE, license="LIC-1", json={"id": 1})
    assert info.value.detail == "Item 1 not found"
    assert info.value.errors == [{"id": 1}]
    assert info.value.response.status_code == 400
    assert len(router.calls) == 1  # 4xx writes are never retried


def test_write_server_error_is_not_retried(client: T3Client, router: Router, sleeps: list[float]) -> None:
    router.add("POST", DISCONTINUE, status=503, json={"detail": "down"})
    with pytest.raises(ServerError):
        client.post(DISCONTINUE, license="LIC-1", json={"id": 1}, submit=True)
    assert len(router.calls) == 1
    assert sleeps == []


def test_write_form_data_and_timeout(client: T3Client, router: Router) -> None:
    router.add("POST", DISCONTINUE, json={"message": "Dry run"})
    client.post(DISCONTINUE, license="LIC-1", data={"id": "1"}, params={"applyDynamicValidation": "true"}, timeout=9)
    request = router.calls[0]
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.content == b"id=1"
    assert request.url.params["applyDynamicValidation"] == "true"
    assert request.extensions["timeout"]["read"] == 9


# --------------------------------------------------------------------------- immediate_write routes


def test_immediate_write_takes_effect(client: T3Client, router: Router, caplog: pytest.LogCaptureFixture) -> None:
    router.add("POST", "/v2/tag-lists", json={"id": "tl-1", "name": "Room A"})
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        result = client.post("/v2/tag-lists", json={"name": "Room A", "licenseNumber": "LIC-1"})
    assert result.dry_run is False
    assert result.message is None
    assert result.data == {"id": "tl-1", "name": "Room A"}
    assert "submit" not in router.calls[0].url.params
    assert "dry run" not in caplog.text


@pytest.mark.parametrize("submit", [True, False])
def test_immediate_write_rejects_submit(client: T3Client, router: Router, submit: bool) -> None:
    with pytest.raises(ValueError, match="takes effect immediately"):
        client.post("/v2/tag-lists", json={"name": "x"}, submit=submit)
    assert router.calls == []


@pytest.mark.parametrize("submit", [True, False])
def test_submit_on_a_read_raises(client: T3Client, router: Router, submit: bool) -> None:
    with pytest.raises(ValueError, match="only applies to writes"):
        client.request("GET", "METRC_ACTIVE_ITEMS", license="LIC-1", submit=submit)
    assert router.calls == []


def test_put(client: T3Client, router: Router) -> None:
    router.add("PUT", "/v2/saved-reports/{public_id}/schedule", json={"message": "Saved"})
    result = client.put("/v2/saved-reports/{public_id}/schedule", public_id="rpt 1", json={"cron": "0 6 * * *"})
    assert result.dry_run is False
    assert result.message == "Saved"
    request = router.calls[0]
    assert request.method == "PUT"
    assert request.url.raw_path == b"/v2/saved-reports/rpt%201/schedule"
    assert body_of(request) == {"cron": "0 6 * * *"}


def test_patch(client: T3Client, router: Router) -> None:
    router.add("PATCH", "/v2/tag-lists/{tag_list_id}", json={"id": "tl-1", "name": "New"})
    result = client.patch("/v2/tag-lists/tl-1", json={"name": "New"})
    assert result.data == {"id": "tl-1", "name": "New"}
    assert router.calls[0].method == "PATCH"
    assert router.calls[0].url.path == "/v2/tag-lists/tl-1"


def test_delete_without_body(client: T3Client, router: Router) -> None:
    router.add("DELETE", "/v2/saved-reports/{public_id}", status=204, content=b"")
    result = client.delete("/v2/saved-reports/{public_id}", public_id="abc")
    assert result.dry_run is False
    assert result.data is None
    assert result.message is None
    assert router.calls[0].method == "DELETE"
    assert router.calls[0].content == b""


def test_delete_with_json_body(client: T3Client, router: Router) -> None:
    router.add("DELETE", "/v2/tag-lists/{tag_list_id}/entries", json={"deleted": 1})
    result = client.delete("/v2/tag-lists/{tag_list_id}/entries", tag_list_id="tl-1", json={"handles": ["A"]})
    assert result.data == {"deleted": 1}
    assert body_of(router.calls[0]) == {"handles": ["A"]}


def test_post_with_files(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/items/images/file", json={"fileId": 42})
    result = client.post(
        "/v2/items/images/file",
        license="LIC-1",
        params={"fileType": "ItemProductImage"},
        files={"file": ("photo.png", b"\x89PNG", "image/png")},
    )
    assert result.data == {"fileId": 42}
    request = router.calls[0]
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b"photo.png" in request.content
    assert request.url.params["licenseNumber"] == "LIC-1"


def test_write_on_a_read_only_endpoint_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError):
        client.post("/v2/auth/whoami", json={})
    assert router.calls == []


# --------------------------------------------------------------------------- body shape and dynamic validation

CHANGE_LOCATIONS = "/v2/packages/change-locations"


def test_object_sent_to_an_array_route_warns(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("POST", CHANGE_LOCATIONS, status=500, json={"detail": "An unexpected error occurred."})
    with pytest.raises(ServerError):
        client.post(CHANGE_LOCATIONS, license="LIC-1", json={"id": 1, "locationId": 2})
    assert "POST /v2/packages/change-locations takes a list of objects, even for one object" in caplog.text
    assert "json=[body]" in caplog.text


def test_list_sent_to_an_object_route_warns(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("POST", DISCONTINUE, json={"message": "Dry run"})
    client.post(DISCONTINUE, license="LIC-1", json=[{"id": 1}])
    assert "POST /v2/items/discontinue takes one object, not a list." in caplog.text


def test_matching_body_shapes_do_not_warn(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("POST", CHANGE_LOCATIONS, json={"message": "Dry run"})
    router.add("POST", DISCONTINUE, json={"message": "Dry run"})
    client.post(CHANGE_LOCATIONS, license="LIC-1", json=[{"id": 1, "locationId": 2}])
    client.post(DISCONTINUE, license="LIC-1", json={"id": 1})
    assert "takes" not in caplog.text


def test_routes_without_a_json_body_schema_do_not_warn(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("POST", "/v2/auth/logout", json={})
    client.post("/v2/auth/logout", json={"anything": True})
    assert "takes" not in caplog.text


def test_dynamic_validation_is_sent(client: T3Client, router: Router) -> None:
    router.add("POST", CHANGE_LOCATIONS, json={"message": "Dry run"})
    result = client.post(CHANGE_LOCATIONS, license="LIC-1", json=[{"id": 1}], dynamic=True)
    assert result.dry_run is True
    assert router.calls[0].url.params["applyDynamicValidation"] == "true"
    assert "submit" not in router.calls[0].url.params


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("put", "/v2/saved-reports/{public_id}/schedule"),
        ("patch", "/v2/saved-reports/{public_id}"),
        ("delete", "/v2/saved-reports/{public_id}"),
    ],
)
def test_dynamic_on_other_methods(client: T3Client, router: Router, method: str, path: str) -> None:
    write = getattr(client, method)
    with pytest.raises(ValueError, match="doesn't offer dynamic validation"):
        write(path, public_id="x", json={}, dynamic=True)
    assert router.calls == []


def test_dynamic_on_a_route_without_it_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match=r"POST /v2/tag-lists doesn't offer dynamic validation"):
        client.post("/v2/tag-lists", json={"name": "x"}, dynamic=True)
    assert router.calls == []
