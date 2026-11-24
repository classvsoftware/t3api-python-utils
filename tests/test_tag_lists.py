"""client.tag_lists and TagList."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest

from t3api_utils.auth.credentials import SecretKeyAuth
from t3api_utils.client import T3Client
from t3api_utils.errors import NotFound, TagListResolveError
from t3api_utils.tag_lists import MAX_ENTRIES, TagList, normalize_entries, read_handles
from tests.conftest import Router, paginated

LIST = {"id": "tl-1", "name": "Room A", "licenseNumber": "LIC-1", "t3EndpointId": "METRC_ACTIVE_PACKAGES", "entryCount": 2}


def body_of(request: httpx2.Request) -> Any:
    return json.loads(request.content)


@pytest.fixture
def lic_client(router: Router) -> Iterator[T3Client]:
    c = T3Client(
        auth=SecretKeyAuth("test-secret-key"),
        license="LIC-1",
        transport=router.transport,
        spec="bundled",
        rate_limit=None,
    )
    yield c
    c.close()


def echo_created(request: httpx2.Request) -> httpx2.Response:
    """POST /v2/tag-lists: echo the list back, wrapped in data."""
    body = body_of(request)
    data = {"id": "tl-new", **{k: v for k, v in body.items() if k != "entries"}}
    data["entryCount"] = len(body.get("entries", []))
    return httpx2.Response(201, json={"data": data})


# --------------------------------------------------------------------------- normalize_entries


def test_normalize_entries(caplog: pytest.LogCaptureFixture) -> None:
    entries: list[Any] = [
        " 1A4000000000000000000001 ",
        {"handle": "1a4000000000000000000001", "note": "repeat, other case"},
        {"handle": "1A4000000000000000000002", "metadata": {"room": "A"}},
        "",
        "   ",
        {"handle": None},
        {"metadata": {"no": "handle"}},
        "1A4000000000000000000003",
        "1A4000000000000000000003",
    ]
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        out = normalize_entries(entries)
    assert out == [
        {"handle": "1A4000000000000000000001"},
        {"handle": "1A4000000000000000000002", "metadata": {"room": "A"}},
        {"handle": "1A4000000000000000000003"},
    ]
    assert "Skipped 2 repeated handle(s)." in caplog.text


def test_normalize_entries_does_not_mutate_input_dicts() -> None:
    entry = {"handle": "  abc  "}
    assert normalize_entries([entry]) == [{"handle": "abc"}]
    assert entry == {"handle": "  abc  "}


def test_normalize_entries_without_repeats_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        assert normalize_entries(["a", "b"]) == [{"handle": "a"}, {"handle": "b"}]
    assert caplog.text == ""


# --------------------------------------------------------------------------- read_handles


def test_read_handles_csv(tmp_path: Path) -> None:
    source = tmp_path / "labels.csv"
    source.write_text("﻿label,room\n A1 ,x\n,y\n  ,z\nA2,w\n", encoding="utf-8")
    assert read_handles(source, "label") == ["A1", "A2"]


@pytest.mark.parametrize("suffix", [".tsv", ".TAB"])
def test_read_handles_tsv_by_suffix(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"labels{suffix}"
    source.write_text("label\troom\nA1\tx, y\nA2\tz\n", encoding="utf-8")
    assert read_handles(source, "label") == ["A1", "A2"]


def test_read_handles_explicit_delimiter(tmp_path: Path) -> None:
    source = tmp_path / "labels.txt"
    source.write_text("label;room\nA1;x\n", encoding="utf-8")
    assert read_handles(str(source), "label", delimiter=";") == ["A1"]


def test_read_handles_missing_column(tmp_path: Path) -> None:
    source = tmp_path / "labels.csv"
    source.write_text("tag,room\nA1,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"labels.csv has no column 'label'. Columns: tag, room"):
        read_handles(source, "label")


def test_read_handles_empty_file(tmp_path: Path) -> None:
    source = tmp_path / "empty.csv"
    source.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="has no column 'label'. Columns: $"):
        read_handles(source, "label")


# --------------------------------------------------------------------------- list / get


def test_list_reads_every_page(client: T3Client, router: Router) -> None:
    lists = [{"id": f"tl-{i}"} for i in range(5)]
    router.add("GET", "/v2/tag-lists", handler=paginated(lists, page_size=2))
    assert client.tag_lists.list() == lists
    params = router.calls[0].url.params
    assert params["pageSize"] == "100"
    assert set(params.keys()) == {"pageSize"}
    assert len(router.calls) == 3


def test_list_license_defaults_to_client_license(lic_client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/tag-lists", handler=paginated([]))
    lic_client.tag_lists.list()
    lic_client.tag_lists.list(license="LIC-2")
    assert [r.url.params["licenseNumber"] for r in router.calls] == ["LIC-1", "LIC-2"]


@pytest.mark.parametrize(("archived", "expected"), [(True, "true"), (False, "false")])
def test_list_filters(client: T3Client, router: Router, archived: bool, expected: str) -> None:
    router.add("GET", "/v2/tag-lists", handler=paginated([]))
    client.tag_lists.list(
        license="LIC-1", visibility="LICENSE", endpoint="METRC_ACTIVE_PACKAGES", archived=archived
    )
    params = router.calls[0].url.params
    assert params["licenseNumber"] == "LIC-1"
    assert params["visibility"] == "LICENSE"
    assert params["t3EndpointId"] == "METRC_ACTIVE_PACKAGES"
    assert params["archived"] == expected


@pytest.mark.parametrize("payload", [{"data": LIST}, LIST], ids=["wrapped", "bare"])
def test_get(client: T3Client, router: Router, payload: dict[str, Any]) -> None:
    router.add("GET", "/v2/tag-lists/{tag_list_id}", json=payload)
    tag_list = client.tag_lists.get("tl-1")
    assert isinstance(tag_list, TagList)
    assert tag_list.data == LIST
    assert router.calls[0].url.path == "/v2/tag-lists/tl-1"


def test_get_url_encodes_the_id(client: T3Client, router: Router) -> None:
    # The decoded path contains a slash, so route it literally.
    router.add("GET", "/v2/tag-lists/a b/c", json=LIST)
    client.tag_lists.get("a b/c")
    assert router.calls[0].url.raw_path == b"/v2/tag-lists/a%20b%2Fc"


def test_get_missing_raises(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/tag-lists/{tag_list_id}", status=404, json={"detail": "no such list"})
    with pytest.raises(NotFound):
        client.tag_lists.get("nope")


# --------------------------------------------------------------------------- create


def test_create_with_default_license(lic_client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    tag_list = lic_client.tag_lists.create("Room A", handles=["A1", "a1", "A2"])
    body = body_of(router.calls[0])
    assert body == {
        "name": "Room A",
        "licenseNumber": "LIC-1",
        "visibility": "USER",
        "entries": [{"handle": "A1"}, {"handle": "A2"}],
    }
    assert tag_list.id == "tl-new"
    assert tag_list.name == "Room A"
    assert len(router.calls) == 1


def test_create_with_all_options(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    tag_list = client.tag_lists.create(
        "Room B",
        license="LIC-2",
        endpoint="METRC_ACTIVE_PACKAGES",
        visibility="LICENSE",
        handles=[{"handle": "A1", "metadata": {"room": "B"}}],
        metadata={"source": "test"},
    )
    assert body_of(router.calls[0]) == {
        "name": "Room B",
        "licenseNumber": "LIC-2",
        "visibility": "LICENSE",
        "t3EndpointId": "METRC_ACTIVE_PACKAGES",
        "metadata": {"source": "test"},
        "entries": [{"handle": "A1", "metadata": {"room": "B"}}],
    }
    assert tag_list.license == "LIC-2"
    assert tag_list.endpoint == "METRC_ACTIVE_PACKAGES"


def test_create_without_handles_sends_no_entries(lic_client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    lic_client.tag_lists.create("Empty")
    assert "entries" not in body_of(router.calls[0])


def test_create_explicit_license_wins(lic_client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    lic_client.tag_lists.create("X", license="LIC-OTHER")
    assert body_of(router.calls[0])["licenseNumber"] == "LIC-OTHER"


def test_create_without_license_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="license="):
        client.tag_lists.create("Room A")
    assert router.calls == []


def test_create_with_more_than_5000_handles(
    lic_client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    handles = [f"H{i:05d}" for i in range(MAX_ENTRIES * 2 + 1)]
    added: list[int] = []

    def add_entries(request: httpx2.Request) -> httpx2.Response:
        count = len(body_of(request)["entries"])
        added.append(count)
        return httpx2.Response(200, json={"created": count, "updated": 0})

    router.add("POST", "/v2/tag-lists", handler=echo_created)
    router.add("POST", "/v2/tag-lists/{tag_list_id}/entries", handler=add_entries)
    router.add("GET", "/v2/tag-lists/{tag_list_id}", json={"data": {"id": "tl-new", "name": "Big", "entryCount": len(handles)}})
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        tag_list = lic_client.tag_lists.create("Big", handles=handles)
    assert "resolves lists of at most 5000 entries" in caplog.text

    create_body = body_of(router.requests("POST", "/v2/tag-lists")[0])
    assert [e["handle"] for e in create_body["entries"]] == handles[:MAX_ENTRIES]
    assert added == [MAX_ENTRIES, 1]
    second = body_of(router.requests("POST", "/v2/tag-lists/tl-new/entries")[0])
    assert second["entries"][0] == {"handle": handles[MAX_ENTRIES]}
    # The list is re-read so its entry count is current.
    assert len(router.requests("GET", "/v2/tag-lists/tl-new")) == 1
    assert tag_list.data["entryCount"] == len(handles)


# --------------------------------------------------------------------------- from_rows / from_csv


def test_from_rows_with_dotted_field(lic_client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    rows: list[dict[str, Any]] = [
        {"item": {"label": "A1"}},
        {"item": {"label": ""}},
        {"item": {}},
        {"other": 1},
        {"item": {"label": 12345}},
    ]
    tag_list = lic_client.tag_lists.from_rows(
        rows, "item.label", name="From rows", endpoint="METRC_ACTIVE_PACKAGES", visibility="LICENSE"
    )
    body = body_of(router.calls[0])
    assert body["entries"] == [{"handle": "A1"}, {"handle": "12345"}]
    assert body["name"] == "From rows"
    assert body["visibility"] == "LICENSE"
    assert body["t3EndpointId"] == "METRC_ACTIVE_PACKAGES"
    assert tag_list.id == "tl-new"


def test_from_csv_name_defaults_to_file_stem(lic_client: T3Client, router: Router, tmp_path: Path) -> None:
    source = tmp_path / "room_a.csv"
    source.write_text("label\nA1\nA2\n", encoding="utf-8")
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    lic_client.tag_lists.from_csv(source, "label")
    body = body_of(router.calls[0])
    assert body["name"] == "room_a"
    assert body["entries"] == [{"handle": "A1"}, {"handle": "A2"}]


def test_from_csv_with_options(client: T3Client, router: Router, tmp_path: Path) -> None:
    source = tmp_path / "labels.txt"
    source.write_text("label|x\nA1|1\n", encoding="utf-8")
    router.add("POST", "/v2/tag-lists", handler=echo_created)
    client.tag_lists.from_csv(
        str(source),
        "label",
        name="Named",
        license="LIC-3",
        endpoint="METRC_ACTIVE_ITEMS",
        visibility="LICENSE",
        delimiter="|",
    )
    assert body_of(router.calls[0]) == {
        "name": "Named",
        "licenseNumber": "LIC-3",
        "visibility": "LICENSE",
        "t3EndpointId": "METRC_ACTIVE_ITEMS",
        "entries": [{"handle": "A1"}],
    }


def test_from_csv_missing_column_sends_nothing(lic_client: T3Client, router: Router, tmp_path: Path) -> None:
    source = tmp_path / "labels.csv"
    source.write_text("tag\nA1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no column 'label'"):
        lic_client.tag_lists.from_csv(source, "label")
    assert router.calls == []


# --------------------------------------------------------------------------- update / add / remove / scan


def test_update(client: T3Client, router: Router) -> None:
    router.add("PATCH", "/v2/tag-lists/{tag_list_id}", json={"data": {**LIST, "name": "Renamed"}})
    tag_list = client.tag_lists.update("tl-1", name="Renamed", archived=True)
    assert body_of(router.calls[0]) == {"name": "Renamed", "archived": True}
    assert tag_list.name == "Renamed"


def test_update_with_empty_response(client: T3Client, router: Router) -> None:
    router.add("PATCH", "/v2/tag-lists/{tag_list_id}", status=204, content=b"")
    assert client.tag_lists.update("tl-1", name="x").data == {}


def test_add_chunks_and_sums_counts(client: T3Client, router: Router) -> None:
    sizes: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        count = len(body_of(request)["entries"])
        sizes.append(count)
        return httpx2.Response(200, json={"data": {"created": count - 1, "updated": 1, "other": "x"}})

    router.add("POST", "/v2/tag-lists/{tag_list_id}/entries", handler=handler)
    entries = [f"H{i}" for i in range(MAX_ENTRIES + 10)] + ["h0"]
    assert client.tag_lists.add("tl-1", entries) == {"created": MAX_ENTRIES + 8, "updated": 2}
    assert sizes == [MAX_ENTRIES, 10]


def test_add_with_missing_counts(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists/{tag_list_id}/entries", status=204, content=b"")
    assert client.tag_lists.add("tl-1", [{"handle": "A1"}]) == {"created": 0, "updated": 0}
    router.add("POST", "/v2/tag-lists/{tag_list_id}/entries", json={"created": None})
    assert client.tag_lists.add("tl-1", ["A1"]) == {"created": 0, "updated": 0}


def test_add_nothing_sends_nothing(client: T3Client, router: Router) -> None:
    assert client.tag_lists.add("tl-1", ["", "  "]) == {"created": 0, "updated": 0}
    assert router.calls == []


def test_remove_chunks_and_merges(client: T3Client, router: Router) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        handles = body_of(request)["handles"]
        return httpx2.Response(
            200,
            json={
                "deleted": len(handles) - 1,
                "handlesNotFound": [handles[0]],
                "complete": True,
                "listId": "tl-1",
            },
        )

    router.add("DELETE", "/v2/tag-lists/{tag_list_id}/entries", handler=handler)
    handles = [f"H{i}" for i in range(MAX_ENTRIES * 2 + 3)]
    result = client.tag_lists.remove("tl-1", handles)
    assert result == {
        "deleted": len(handles) - 3,
        "handlesNotFound": ["H0", f"H{MAX_ENTRIES}", f"H{MAX_ENTRIES * 2}"],
        "complete": True,
        "listId": "tl-1",
    }
    requests = router.requests("DELETE", "/v2/tag-lists/tl-1/entries")
    assert [len(body_of(r)["handles"]) for r in requests] == [MAX_ENTRIES, MAX_ENTRIES, 3]


def test_scan_with_and_without_timestamp(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists/{tag_list_id}/scan", json={"data": {"scanned": 2, "alreadyScanned": []}})
    assert client.tag_lists.scan("tl-1", ["A1", "A2", "a2"]) == {"scanned": 2, "alreadyScanned": []}
    assert body_of(router.calls[0]) == {"handles": ["A1", "A2"]}
    client.tag_lists.scan("tl-1", ["A1"], scanned_at="2026-11-23T10:00:00Z")
    assert body_of(router.calls[1]) == {"handles": ["A1"], "scannedAt": "2026-11-23T10:00:00Z"}


# --------------------------------------------------------------------------- entries / resolve


def test_entries(client: T3Client, router: Router) -> None:
    entries = [{"handle": f"H{i}"} for i in range(5)]
    router.add("GET", "/v2/tag-lists/{tag_list_id}/entries", handler=paginated(entries, page_size=2))
    assert client.tag_lists.entries("tl-1") == entries
    assert router.calls[0].url.params["pageSize"] == "100"
    assert {r.url.path for r in router.calls} == {"/v2/tag-lists/tl-1/entries"}


def test_resolve(client: T3Client, router: Router) -> None:
    packages = [{"id": i, "label": f"P{i}"} for i in range(5)]
    router.add("GET", "/v2/tag-lists/{tag_list_id}/resolve", handler=paginated(packages, page_size=2))
    assert client.tag_lists.resolve("tl-1", progress=True) == packages
    assert set(router.calls[0].url.params.keys()) == set()
    assert len(router.calls) == 3


def test_resolve_parameters(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/tag-lists/{tag_list_id}/resolve", handler=paginated([]))
    client.tag_lists.resolve(
        "tl-1", "METRC_ACTIVE_ITEMS", mask=["id", "name"], include=["entry", "metadata"]
    )
    params = router.calls[0].url.params
    assert params["t3EndpointId"] == "METRC_ACTIVE_ITEMS"
    assert params["collectionMask"] == "id,name"
    assert params.get_list("include") == ["entry", "metadata"]
    client.tag_lists.resolve("tl-1", mask="id")
    assert router.calls[1].url.params["collectionMask"] == "id"


def test_resolve_422_raises_with_per_handle_errors(client: T3Client, router: Router) -> None:
    errors = [
        {"handle": "A1", "reason": "NOT_FOUND", "matchCount": 0},
        {"handle": "A2", "reason": "AMBIGUOUS", "matchCount": 2},
    ]
    router.add(
        "GET",
        "/v2/tag-lists/{tag_list_id}/resolve",
        status=422,
        json={"title": "Unresolved entries", "detail": "2 handles did not resolve", "errors": errors},
        headers={"content-type": "application/problem+json"},
    )
    with pytest.raises(TagListResolveError) as info:
        client.tag_lists.resolve("tl-1")
    assert info.value.errors == errors
    assert info.value.status_code == 422
    assert info.value.detail == "2 handles did not resolve"


# --------------------------------------------------------------------------- TagList


def test_tag_list_properties() -> None:
    owner = T3Client(auth=SecretKeyAuth("k"), spec="bundled").tag_lists
    tag_list = TagList(owner, dict(LIST))
    assert tag_list.id == "tl-1"
    assert tag_list.name == "Room A"
    assert tag_list.license == "LIC-1"
    assert tag_list.endpoint == "METRC_ACTIVE_PACKAGES"
    assert tag_list["entryCount"] == 2
    assert repr(tag_list) == "<TagList tl-1 'Room A' entries=2>"
    owner._client.close()


def test_tag_list_optional_properties() -> None:
    owner = T3Client(auth=SecretKeyAuth("k"), spec="bundled").tag_lists
    tag_list = TagList(owner, {"id": 7})
    assert tag_list.id == "7"
    assert tag_list.name is None
    assert tag_list.license is None
    assert tag_list.endpoint is None
    assert repr(tag_list) == "<TagList 7 None entries=None>"
    with pytest.raises(KeyError):
        tag_list["missing"]
    owner._client.close()


def test_tag_list_bound_methods(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/tag-lists/{tag_list_id}", json={"data": LIST})
    tag_list = client.tag_lists.get("tl-1")

    router.add("GET", "/v2/tag-lists/{tag_list_id}", json={"data": {**LIST, "entryCount": 3}})
    assert tag_list.refresh() is tag_list
    assert tag_list["entryCount"] == 3

    router.add("PATCH", "/v2/tag-lists/{tag_list_id}", json={"data": {**LIST, "name": "Renamed"}})
    assert tag_list.update(name="Renamed") is tag_list
    assert tag_list.name == "Renamed"

    router.add("POST", "/v2/tag-lists/{tag_list_id}/entries", json={"created": 1, "updated": 0})
    assert tag_list.add(["A3"]) == {"created": 1, "updated": 0}

    router.add("DELETE", "/v2/tag-lists/{tag_list_id}/entries", json={"deleted": 1})
    assert tag_list.remove(["A3"]) == {"deleted": 1}

    router.add("POST", "/v2/tag-lists/{tag_list_id}/scan", json={"scanned": 1})
    assert tag_list.scan(["A1"], scanned_at="2026-01-01T00:00:00Z") == {"scanned": 1}
    assert body_of(router.calls[-1]) == {"handles": ["A1"], "scannedAt": "2026-01-01T00:00:00Z"}

    router.add("GET", "/v2/tag-lists/{tag_list_id}/entries", handler=paginated([{"handle": "A1"}]))
    assert tag_list.entries() == [{"handle": "A1"}]

    router.add("GET", "/v2/tag-lists/{tag_list_id}/resolve", handler=paginated([{"id": 1}]))
    assert tag_list.resolve("METRC_ACTIVE_PACKAGES", mask="id", include=["entry"], progress=False) == [{"id": 1}]
    params = router.calls[-1].url.params
    assert params["t3EndpointId"] == "METRC_ACTIVE_PACKAGES"
    assert params["collectionMask"] == "id"
    assert params["include"] == "entry"

    assert {r.url.path.split("/")[3] for r in router.calls} == {"tl-1"}
