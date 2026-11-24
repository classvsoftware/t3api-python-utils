"""`t3api endpoints/pull/report/inspect/tag-lists/spec`."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

import t3api_utils as t3
import t3api_utils.tui
from t3api_utils.spec.loader import SpecSource, bundled_spec
from t3api_utils.spec.registry import KINDS, Registry
from t3api_utils.tui import inspector
from tests._cli_helpers import TINY_SPEC, Prompts, invoke, save_profile
from tests._cli_helpers import api, cli_env, prompts  # noqa: F401  (fixtures)
from tests.conftest import Router, paginated

ITEMS = [
    {"id": 1, "name": "Flower", "licenseNumber": "LIC-1", "dataModel": "METRC_ITEM"},
    {"id": 2, "name": "Pre-roll", "licenseNumber": "LIC-1", "dataModel": "METRC_ITEM"},
    {"id": 3, "name": "Vape", "licenseNumber": "LIC-1", "dataModel": "METRC_ITEM"},
]


def bundled_registry() -> Registry:
    return Registry(bundled_spec(), SpecSource(kind="bundled", host="api.trackandtrace.tools"))


class InspectorSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Mapping[str, Any]], str]] = []

    def __call__(self, rows: Sequence[Mapping[str, Any]], *, title: str = "rows") -> None:
        self.calls.append((list(rows), title))


@pytest.fixture
def inspector_spy(monkeypatch: pytest.MonkeyPatch) -> InspectorSpy:
    spy = InspectorSpy()
    monkeypatch.setattr(inspector, "run", spy)
    return spy


@pytest.fixture
def no_textual(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the inspector import fail the way it does without the tui extra."""
    monkeypatch.setitem(sys.modules, "textual", None)
    monkeypatch.delitem(sys.modules, "t3api_utils.tui.inspector")
    monkeypatch.delattr(t3api_utils.tui, "inspector")


# --------------------------------------------------------------------------- endpoints


def test_endpoints_search_by_words_and_kind(api: Router) -> None:
    result = invoke("endpoints", "active items", "--kind", "collection")
    assert result.exit_code == 0
    assert "METRC_ACTIVE_ITEMS" in result.stdout
    assert "GET /v2/items" in result.stdout
    assert "ITEMS_REPORT" not in result.stdout
    assert api.calls == []


def test_endpoints_without_a_query_lists_everything(api: Router) -> None:
    result = invoke("endpoints")
    assert result.exit_code == 0
    assert f"{len(bundled_registry().endpoints)} endpoint(s)" in result.stdout


def test_endpoints_rejects_an_unknown_kind(api: Router) -> None:
    result = invoke("endpoints", "--kind", "bogus")
    assert result.exit_code == 1
    assert f"--kind must be one of {', '.join(KINDS)}." in result.stderr


def test_endpoints_fetch_the_live_spec_from_the_profile_host(
    api: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("T3_SPEC")
    api.add("GET", "/v2/spec/openapi.json", json=TINY_SPEC)
    save_profile("default", api_host="https://sandbox.example")
    result = invoke("endpoints")
    assert result.exit_code == 0
    assert "1 endpoint(s)" in result.stdout
    assert "WIDGETS" in result.stdout and "GET /v2/widgets" in result.stdout
    [request] = api.requests("GET", "/v2/spec/openapi.json")
    assert request.url.host == "sandbox.example"


# --------------------------------------------------------------------------- pull


@pytest.mark.parametrize("suffix", [".csv", ".json", ".jsonl"])
def test_pull_writes_by_extension(api: Router, suffix: str) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS, page_size=2))
    save_profile("default")
    result = invoke("pull", "METRC_ACTIVE_ITEMS", "-l", "LIC-1", "-o", f"items{suffix}")
    assert result.exit_code == 0, result.output
    rows = t3.read_rows(f"items{suffix}")
    assert [str(r["id"]) for r in rows] == ["1", "2", "3"]
    assert f"Wrote 3 rows to items{suffix}" in result.stderr
    assert {r.url.params["licenseNumber"] for r in api.requests("GET", "/v2/items")} == {"LIC-1"}


def test_pull_json_keeps_types(api: Router) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS))
    save_profile("default")
    invoke("pull", "METRC_ACTIVE_ITEMS", "-l", "LIC-1", "-o", "items.json")
    assert json.loads(Path("items.json").read_text(encoding="utf-8")) == ITEMS
    invoke("pull", "METRC_ACTIVE_ITEMS", "-l", "LIC-1", "-o", "items.jsonl")
    lines = Path("items.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == ITEMS


def test_pull_default_output_is_csv_in_the_current_folder(api: Router) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS))
    save_profile("default")
    result = invoke("pull", "METRC_ACTIVE_ITEMS", "-l", "LIC-1")
    assert result.exit_code == 0
    [written] = list(Path.cwd().glob("*.csv"))
    assert written.name.startswith("METRC_ITEM__LIC-1__")
    assert len(t3.read_rows(written)) == 3


def test_pull_passes_filters_sort_mask_and_licenses(api: Router) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS[:1]))
    save_profile("default")
    result = invoke(
        "pull", "/v2/items",
        "-l", "LIC-1", "-l", "LIC-2",
        "--filter", "name__contains:flower", "-f", "id__gt:0",
        "--sort", "name:asc",
        "--mask", "id,name",
        "-o", "out.csv",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    requests = api.requests("GET", "/v2/items")
    assert [r.url.params["licenseNumber"] for r in requests] == ["LIC-1", "LIC-2"]
    params = requests[0].url.params
    assert params.get_list("filter") == ["name__contains:flower", "id__gt:0"]
    assert params["sort"] == "name:asc"
    assert params["collectionMask"] == "id,name"
    assert "Wrote 2 rows" in result.stderr


def test_pull_inspect_opens_the_inspector_instead_of_writing(api: Router, inspector_spy: InspectorSpy) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS))
    save_profile("default")
    result = invoke("pull", "METRC_ACTIVE_ITEMS", "-l", "LIC-1", "--inspect", "-o", "unused.csv")
    assert result.exit_code == 0
    assert inspector_spy.calls == [(ITEMS, "METRC_ACTIVE_ITEMS")]
    assert not Path("unused.csv").exists()
    assert "Wrote" not in result.stderr


def _collection(endpoint_id: str | None, summary: str, *, license_param: bool) -> dict[str, Any]:
    params = [{"name": "licenseNumber", "in": "query", "required": True, "schema": {"type": "string"}}]
    op: dict[str, Any] = {
        "summary": summary,
        "parameters": params if license_param else [],
        "responses": {
            "200": {
                "description": "ok",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pagination"}}},
            }
        },
    }
    if endpoint_id:
        op["x-t3-endpoint-id"] = endpoint_id
    return {"get": op}


PICKER_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"version": "test"},
    "components": {"schemas": {"Pagination": {"type": "object"}}},
    "paths": {
        "/v2/widgets": _collection("WIDGETS", "Every widget", license_param=True),
        "/v2/saved-reports": _collection(None, "Saved reports", license_param=False),
    },
}


def test_pull_picks_the_endpoint_when_omitted(
    api: Router, prompts: Prompts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("T3_SPEC")
    api.add("GET", "/v2/spec/openapi.json", json=PICKER_SPEC)
    reports = [{"id": "r1", "name": "Weekly"}]
    api.add("GET", "/v2/saved-reports", handler=paginated(reports))
    save_profile("default")
    # Sorted with named endpoints first: 1 = WIDGETS, 2 = /v2/saved-reports (no ID).
    prompts.answer("Number, or text to filter", "2")
    result = invoke("pull", "-o", "saved.json")
    assert result.exit_code == 0, result.output
    assert "Every widget" in result.stderr and "Saved reports" in result.stderr
    assert json.loads(Path("saved.json").read_text(encoding="utf-8")) == reports
    # /v2/saved-reports takes no licenseNumber, so no license picker even in a terminal.
    assert api.requests("GET", "/v2/licenses") == []
    assert "licenseNumber" not in api.requests("GET", "/v2/saved-reports")[0].url.params


def test_pull_picked_endpoint_then_license(
    api: Router, prompts: Prompts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("T3_SPEC")
    api.add("GET", "/v2/spec/openapi.json", json=PICKER_SPEC)
    api.add("GET", "/v2/widgets", handler=paginated([{"id": 1}]))
    api.add("GET", "/v2/licenses", json=[{"licenseNumber": "LIC-1"}, {"licenseNumber": "LIC-2"}])
    save_profile("default")
    prompts.answer("Number, or text to filter", "widget", "1")
    prompts.answer("Number", "1")
    result = invoke("pull", "-o", "widgets.csv")
    assert result.exit_code == 0, result.output
    assert api.requests("GET", "/v2/widgets")[0].url.params["licenseNumber"] == "LIC-1"


def test_pull_endpoint_picker_by_id(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS))
    save_profile("default", license="LIC-1")
    prompts.answer("Number, or text to filter", "METRC_ACTIVE_ITEMS", "1")
    result = invoke("pull", "-o", "items.csv")
    assert result.exit_code == 0, result.output
    assert "Wrote 3 rows to items.csv" in result.stderr


def test_pull_endpoint_picker_needs_a_terminal(api: Router) -> None:
    save_profile("default")
    result = invoke("pull")
    assert result.exit_code == 1
    assert "Endpoints needs a terminal to ask in." in result.stderr


def test_pull_picks_a_license_when_needed(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS))
    api.add(
        "GET",
        "/v2/licenses",
        json=[{"licenseNumber": "LIC-1", "licenseName": "North"}, {"licenseNumber": "LIC-2", "licenseName": "South"}],
    )
    save_profile("default")
    prompts.answer("Number", "2")
    result = invoke("pull", "METRC_ACTIVE_ITEMS", "-o", "items.csv")
    assert result.exit_code == 0, result.output
    assert {r.url.params["licenseNumber"] for r in api.requests("GET", "/v2/items")} == {"LIC-2"}


def test_pull_uses_the_profile_license_without_asking(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/items", handler=paginated(ITEMS))
    save_profile("default", license="LIC-9")
    result = invoke("pull", "METRC_ACTIVE_ITEMS", "-o", "items.csv")
    assert result.exit_code == 0
    assert prompts.asked == []
    assert {r.url.params["licenseNumber"] for r in api.requests("GET", "/v2/items")} == {"LIC-9"}


def test_pull_without_terminal_or_license_explains(api: Router) -> None:
    save_profile("default")
    result = invoke("pull", "METRC_ACTIVE_ITEMS")
    assert result.exit_code == 1
    assert "GET /v2/items (METRC_ACTIVE_ITEMS) needs: license=." in result.stderr
    assert api.calls == []


def test_pull_unknown_endpoint(api: Router) -> None:
    save_profile("default")
    result = invoke("pull", "METRC_ACTIVE_ITEMZ", "-l", "LIC-1")
    assert result.exit_code == 1
    assert "'METRC_ACTIVE_ITEMZ' is not in the T3 OpenAPI spec." in result.stderr


def test_pull_non_collection_shows_kinds_in_brackets(api: Router) -> None:
    save_profile("default")
    result = invoke("pull", "ITEMS_REPORT")
    assert result.exit_code == 1
    assert "[report]" in result.stderr


# --------------------------------------------------------------------------- report


def test_report_url_prints_a_secret_key_url(api: Router) -> None:
    save_profile("default", secret="sk-default-0001")
    result = invoke("report", "ITEMS_REPORT", "-l", "LIC-1", "--url", "--columns", "id,name")
    assert result.exit_code == 0, result.output
    url = result.stdout.strip()
    assert url.startswith("https://api.trackandtrace.tools/v2/items/report?")
    assert "licenseNumber=LIC-1" in url
    assert "contentType=csv" in url
    assert "columns=id%2Cname" in url
    assert "secretKey=sk-default-0001" in url
    assert "Anyone with this URL can use your secret key." in result.stderr
    assert api.calls == []


def test_report_url_with_format(api: Router) -> None:
    save_profile("default")
    result = invoke("report", "ITEMS_REPORT", "-l", "LIC-1", "--url", "--format", "xlsx")
    assert "contentType=xlsx" in result.stdout


def test_report_url_needs_a_secret_key(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T3_JWT", "header.payload.signature")
    result = invoke("report", "ITEMS_REPORT", "-l", "LIC-1", "--url")
    assert result.exit_code == 1
    assert "report_url() needs a secret key" in result.stderr


def test_report_google_sheets_prints_the_sheet_url(api: Router) -> None:
    api.add(
        "GET",
        "/v2/items/report",
        json={"ok": True},
        headers={"Location": "https://docs.google.com/spreadsheets/d/abc"},
    )
    save_profile("default", license="LIC-1")
    result = invoke("report", "ITEMS_REPORT", "--format", "googleSheets")
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "https://docs.google.com/spreadsheets/d/abc"
    [request] = api.requests("GET", "/v2/items/report")
    assert request.url.params["contentType"] == "googleSheets"
    assert request.url.params["licenseNumber"] == "LIC-1"


@pytest.mark.parametrize(
    ("output", "fmt", "content_type"),
    [
        ("out.xlsx", None, "xlsx"),
        ("OUT.CSV", None, "csv"),
        ("report", None, "csv"),
        ("data.dat", "json", "json"),
    ],
)
def test_report_to_a_file_infers_the_format(
    api: Router, output: str, fmt: str | None, content_type: str
) -> None:
    api.add("GET", "/v2/items/report", content=b"report-bytes", headers={"content-type": "application/octet-stream"})
    save_profile("default")
    args = ["report", "ITEMS_REPORT", "-l", "LIC-1", "-o", output]
    if fmt:
        args += ["--format", fmt]
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    assert Path(output).read_bytes() == b"report-bytes"
    assert api.requests("GET", "/v2/items/report")[0].url.params["contentType"] == content_type
    assert f"Saved the report to {output}" in result.stderr


def test_report_default_file_name(api: Router) -> None:
    api.add("GET", "/v2/items/report", content=b"a,b\n", headers={"content-type": "text/csv"})
    save_profile("default")
    result = invoke(
        "report", "/v2/items/report", "-l", "LIC-1", "-f", "name__contains:x", "--sort", "name:asc"
    )
    assert result.exit_code == 0, result.output
    [written] = list(Path.cwd().iterdir())
    assert written.name.startswith("v2_items_report__") and written.suffix == ".csv"
    params = api.requests("GET", "/v2/items/report")[0].url.params
    assert params["contentType"] == "csv"
    assert params["filter"] == "name__contains:x"
    assert params["sort"] == "name:asc"


def test_report_unknown_format_from_extension(api: Router) -> None:
    save_profile("default")
    result = invoke("report", "ITEMS_REPORT", "-l", "LIC-1", "-o", "out.txt")
    assert result.exit_code == 1
    assert "format must be one of" in result.stderr
    assert api.calls == []


def test_report_without_a_license(api: Router) -> None:
    save_profile("default")
    result = invoke("report", "ITEMS_REPORT")
    assert result.exit_code == 1
    assert "Pass licenses=[...]" in result.stderr


# --------------------------------------------------------------------------- inspect


def test_inspect_a_json_file(inspector_spy: InspectorSpy) -> None:
    Path("rows.json").write_text(json.dumps(ITEMS), encoding="utf-8")
    result = invoke("inspect", "rows.json")
    assert result.exit_code == 0
    assert inspector_spy.calls == [(ITEMS, "rows.json")]


def test_inspect_a_csv_file(inspector_spy: InspectorSpy) -> None:
    t3.to_csv(ITEMS, "rows.csv")
    result = invoke("inspect", "rows.csv")
    assert result.exit_code == 0
    [(rows, title)] = inspector_spy.calls
    assert title == "rows.csv"
    assert [r["name"] for r in rows] == ["Flower", "Pre-roll", "Vape"]


def test_inspect_an_empty_file(inspector_spy: InspectorSpy) -> None:
    Path("empty.json").write_text("[]", encoding="utf-8")
    result = invoke("inspect", "empty.json")
    assert result.exit_code == 0
    assert "No rows to inspect." in result.stderr
    assert inspector_spy.calls == []


def test_inspect_a_missing_file() -> None:
    result = invoke("inspect", "missing.json")
    assert result.exit_code == 1
    assert "missing.json" in result.stderr


def test_inspect_invalid_json() -> None:
    Path("bad.json").write_text("{not json", encoding="utf-8")
    result = invoke("inspect", "bad.json")
    assert result.exit_code == 1
    assert "line 1 column 2" in result.stderr


@pytest.mark.usefixtures("no_textual")
def test_inspect_without_textual_names_the_extra() -> None:
    Path("rows.json").write_text(json.dumps(ITEMS), encoding="utf-8")
    result = invoke("inspect", "rows.json")
    assert result.exit_code == 1
    assert f"✗ {t3.TUI_HINT}" in result.stderr


# --------------------------------------------------------------------------- tag lists


def test_tag_lists_list(api: Router) -> None:
    lists: list[dict[str, Any]] = [
        {"id": "tl1", "name": "Room [A]", "licenseNumber": "LIC-1", "t3EndpointId": None, "entryCount": 3, "scannedCount": 1},
        {"id": "tl2", "name": "Vault", "licenseNumber": "LIC-1", "t3EndpointId": "METRC_ACTIVE_PACKAGES"},
    ]
    api.add("GET", "/v2/tag-lists", handler=paginated(lists, page_size=100))
    save_profile("default")
    result = invoke("tag-lists", "list", "-l", "LIC-1")
    assert result.exit_code == 0, result.output
    assert "Room [A]" in result.stdout
    assert "METRC_ACTIVE_PACKAGES" in result.stdout
    [request] = api.requests("GET", "/v2/tag-lists")
    assert request.url.params["licenseNumber"] == "LIC-1"


def test_tag_lists_list_without_license_filter(api: Router) -> None:
    api.add("GET", "/v2/tag-lists", handler=paginated([], page_size=100))
    save_profile("default")
    result = invoke("tag-lists", "list")
    assert result.exit_code == 0
    assert "licenseNumber" not in api.requests("GET", "/v2/tag-lists")[0].url.params


def _labels_csv() -> Path:
    path = Path("labels.csv")
    path.write_text("label,room\nTAG-A,1\nTAG-B,2\ntag-a,3\n", encoding="utf-8")
    return path


def test_tag_lists_create_from_a_csv_column(api: Router) -> None:
    api.add("POST", "/v2/tag-lists", json={"data": {"id": "tl9", "name": "labels", "entryCount": 2}})
    save_profile("default")
    _labels_csv()
    result = invoke("tag-lists", "create", "labels.csv", "--column", "label", "-l", "LIC-1")
    assert result.exit_code == 0, result.output
    assert result.stdout == "tl9\n"
    assert "Created tag list 'labels' with 2 entries." in result.stderr
    [request] = api.requests("POST", "/v2/tag-lists")
    assert json.loads(request.content) == {
        "name": "labels",
        "licenseNumber": "LIC-1",
        "visibility": "USER",
        "entries": [{"handle": "TAG-A"}, {"handle": "TAG-B"}],
    }


def test_tag_lists_create_shared_with_name_and_endpoint(api: Router) -> None:
    api.add("POST", "/v2/tag-lists", json={"id": "tl10", "name": "Room A"})
    save_profile("default", license="LIC-7")
    _labels_csv()
    result = invoke(
        "tag-lists", "create", "labels.csv", "-c", "label",
        "--name", "Room A", "-e", "METRC_ACTIVE_PACKAGES", "--shared",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "Created tag list 'Room A' with ? entries." in result.stderr
    sent = json.loads(api.requests("POST", "/v2/tag-lists")[0].content)
    assert sent["visibility"] == "LICENSE"
    assert sent["licenseNumber"] == "LIC-7"
    assert sent["t3EndpointId"] == "METRC_ACTIVE_PACKAGES"


def test_tag_lists_create_missing_column(api: Router) -> None:
    save_profile("default", license="LIC-1")
    _labels_csv()
    result = invoke("tag-lists", "create", "labels.csv", "--column", "tag")
    assert result.exit_code == 1
    assert "labels.csv has no column 'tag'. Columns: label, room" in result.stderr


def test_tag_lists_create_needs_a_license(api: Router) -> None:
    save_profile("default")
    _labels_csv()
    result = invoke("tag-lists", "create", "labels.csv", "--column", "label")
    assert result.exit_code == 1
    assert "needs license=" in result.stderr


def test_tag_lists_resolve_to_a_file(api: Router) -> None:
    objects = [{"id": 10, "label": "TAG-A"}, {"id": 11, "label": "TAG-B"}]
    api.add("GET", "/v2/tag-lists/{id}/resolve", handler=paginated(objects))
    save_profile("default")
    result = invoke("tag-lists", "resolve", "tl9", "-e", "METRC_ACTIVE_PACKAGES", "-o", "resolved.json")
    assert result.exit_code == 0, result.output
    assert json.loads(Path("resolved.json").read_text(encoding="utf-8")) == objects
    assert "Resolved 2 objects to resolved.json" in result.stderr
    request = api.requests("GET", "/v2/tag-lists/tl9/resolve")[0]
    assert request.url.params["t3EndpointId"] == "METRC_ACTIVE_PACKAGES"


def test_tag_lists_resolve_failure_shows_the_handles(api: Router) -> None:
    errors: list[Any] = [
        {"handle": "TAG-A", "reason": "NOT_FOUND", "matchCount": 0},
        {"handle": "TAG-B", "reason": "AMBIGUOUS", "matchCount": 2},
        "not-a-dict",
    ]
    errors += [{"handle": f"handle-{i:03d}", "reason": "NOT_FOUND", "matchCount": 0} for i in range(3, 60)]
    api.add(
        "GET",
        "/v2/tag-lists/{id}/resolve",
        status=422,
        json={"detail": "59 handles didn't resolve", "code": "TAG_LIST_UNRESOLVED_ENTRIES", "errors": errors},
    )
    save_profile("default")
    result = invoke("tag-lists", "resolve", "tl9")
    assert result.exit_code == 1
    err = result.stderr
    assert "✗ 59 handles didn't resolve" in err
    assert "Handles that didn't resolve" in err
    assert "TAG-A" in err and "NOT_FOUND" in err
    assert "TAG-B" in err and "AMBIGUOUS" in err
    assert "not-a-dict" not in err
    assert "handle-049" in err
    assert "handle-050" not in err  # only the first 50 errors are listed
    assert list(Path.cwd().iterdir()) == []


# --------------------------------------------------------------------------- spec


def test_spec_info_bundled(api: Router) -> None:
    result = invoke("spec", "info")
    assert result.exit_code == 0
    out = result.stdout
    registry = bundled_registry()
    assert "Spec: bundled copy (shipped with t3api-utils)" in out
    assert f"Version: {registry.version}" in out
    assert f"{len(registry.endpoints)} operations" in out
    collections = len(registry.list("collection"))
    assert any("collection" in line and str(collections) in line for line in out.splitlines())


def test_spec_info_live_without_version(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("T3_SPEC")
    api.add("GET", "/v2/spec/openapi.json", json=TINY_SPEC)
    result = invoke("spec", "info")
    assert result.exit_code == 0, result.output
    assert "Spec: live copy for api.trackandtrace.tools" in result.stdout
    assert "Version:" not in result.stdout
    assert "1 operations" in result.stdout


def test_spec_refresh_caches_the_live_spec(api: Router, isolated: Path) -> None:
    api.add("GET", "/v2/spec/openapi.json", json=TINY_SPEC, headers={"ETag": '"v1"'})
    result = invoke("spec", "refresh")
    assert result.exit_code == 0, result.output
    assert "Fetched the spec from https://api.trackandtrace.tools: 1 operations." in result.stderr
    assert list((isolated / "cache" / "spec").glob("*.json.gz"))


def test_spec_refresh_failure(api: Router) -> None:
    api.add("GET", "/v2/spec/openapi.json", json={"detail": "gone"}, status=404)
    result = invoke("spec", "refresh")
    assert result.exit_code == 1
    assert "Couldn't fetch the T3 spec from https://api.trackandtrace.tools" in result.stderr
