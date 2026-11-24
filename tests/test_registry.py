"""spec/registry.py: classification, lookup and parameter checks."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from t3api_utils.errors import SpecError, UnknownEndpoint
from t3api_utils.spec import KINDS, Endpoint, Param, Registry
from t3api_utils.spec.loader import SpecSource, bundled_spec
from t3api_utils.spec.registry import XLSX, _Resolver


@pytest.fixture(scope="module")
def bundled() -> Registry:
    return Registry(bundled_spec())


def ok_json(schema: dict[str, Any]) -> dict[str, Any]:
    return {"200": {"description": "ok", "content": {"application/json": {"schema": schema}}}}


def ok_content(*types: str) -> dict[str, Any]:
    return {"200": {"description": "ok", "content": {t: {} for t in types}}}


PAGINATED = {"allOf": [{"$ref": "#/components/schemas/Pagination"}, {"type": "object"}]}


def registry(paths: dict[str, Any], **extra: Any) -> Registry:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"version": "test"},
        "paths": paths,
        "components": {"schemas": {"Pagination": {"type": "object"}}},
    }
    for key, value in extra.items():
        if key == "components":
            for section, entries in value.items():
                spec["components"].setdefault(section, {}).update(entries)
        else:
            spec[key] = value
    return Registry(spec)


def only(reg: Registry) -> Endpoint:
    [ep] = reg.endpoints
    return ep


# --------------------------------------------------------------------------- bundled spec


@pytest.mark.parametrize(
    ("name", "method", "kind_hint", "path", "kind"),
    [
        ("METRC_ACTIVE_ITEMS", "GET", "collection", "/v2/items", "collection"),
        ("METRC_ACTIVE_ITEMS", "GET", "object", "/v2/items/{object_id}", "object"),
        ("ITEMS_REPORT", "GET", None, "/v2/items/report", "report"),
        ("/v2/items/discontinue", "POST", None, "/v2/items/discontinue", "metrc_write"),
        ("/v2/tag-lists", "POST", None, "/v2/tag-lists", "immediate_write"),
        ("/v2/tag-lists", "GET", None, "/v2/tag-lists", "collection"),
        ("/v2/tag-lists/{tag_list_id}/resolve", "GET", None, "/v2/tag-lists/{tag_list_id}/resolve", "collection"),
        ("/v2/licenses", "GET", None, "/v2/licenses", "other"),
        ("/v2/auth/whoami", "GET", None, "/v2/auth/whoami", "other"),
        ("/v2/transfers/manifest", "GET", None, "/v2/transfers/manifest", "file"),
        ("/v2/coa/{public_id}.pdf", "GET", None, "/v2/coa/{public_id}.pdf", "file"),
    ],
)
def test_bundled_named_endpoints(
    bundled: Registry, name: str, method: str, kind_hint: Any, path: str, kind: str
) -> None:
    ep = bundled.endpoint(name, method=method, kind=kind_hint)
    assert ep.path == path
    assert ep.method == method
    assert ep.kind == kind


def test_bundled_active_items_details(bundled: Registry) -> None:
    ep = bundled.endpoint("METRC_ACTIVE_ITEMS", kind="collection")
    assert ep.id == "METRC_ACTIVE_ITEMS"
    # The " · METRC_ACTIVE_ITEMS" suffix the spec adds to summaries is stripped.
    assert ep.summary == "List of active items"
    lic = ep.param("licenseNumber")
    assert lic is not None and lic.required and lic.location == "query"
    flt = ep.param("filter")
    assert flt is not None and flt.is_array
    assert not ep.is_write
    assert ep.public is False


def test_bundled_writes_and_public_routes(bundled: Registry) -> None:
    discontinue = bundled.endpoint("/v2/items/discontinue")
    assert discontinue.is_write
    assert discontinue.body_required and discontinue.has_body
    assert discontinue.param("submit") is not None
    assert bundled.endpoint("/v2/auth/secretkey", method="POST").public is True
    assert bundled.endpoint("/v2/auth/secretkey", method="GET").public is False


def test_bundled_report_response_types(bundled: Registry) -> None:
    report = bundled.endpoint("ITEMS_REPORT")
    assert "text/csv" in report.response_types
    assert XLSX in report.response_types


def test_bundled_every_kind_present_and_list_filters(bundled: Registry) -> None:
    for kind in KINDS:
        found = bundled.list(kind)  # type: ignore[arg-type]
        assert found, kind
        assert all(ep.kind == kind for ep in found)
    assert len(bundled.list()) == len(bundled.endpoints)
    assert bundled.version


def test_bundled_concrete_paths_match_templates(bundled: Registry) -> None:
    obj = bundled.endpoint("/v2/items/123")
    assert obj.path == "/v2/items/{object_id}"
    assert obj.kind == "object"
    resolve = bundled.endpoint("/v2/tag-lists/77/resolve")
    assert resolve.path == "/v2/tag-lists/{tag_list_id}/resolve"
    # A literal path wins over a template that would also match it.
    assert bundled.endpoint("/v2/items/discontinue").path == "/v2/items/discontinue"


def test_bundled_id_picks_by_path_params(bundled: Registry) -> None:
    assert bundled.endpoint("METRC_ACTIVE_ITEMS").kind == "collection"
    assert bundled.endpoint("METRC_ACTIVE_ITEMS", path_params=["object_id"]).kind == "object"


def test_bundled_find(bundled: Registry) -> None:
    found = bundled.find("active items")
    assert any(ep.id == "METRC_ACTIVE_ITEMS" for ep in found)
    reports = bundled.find("items", kind="report")
    assert reports and all(ep.kind == "report" for ep in reports)
    assert any(ep.id == "ITEMS_REPORT" for ep in reports)


def test_bundled_unknown_id_suggests(bundled: Registry) -> None:
    with pytest.raises(UnknownEndpoint) as info:
        bundled.endpoint("METRC_ACTIVE_ITEM")
    assert "METRC_ACTIVE_ITEMS" in info.value.suggestions
    with pytest.raises(UnknownEndpoint) as by_path:
        bundled.endpoint("/v2/itemz")
    assert "/v2/items" in by_path.value.suggestions


def test_bundled_ids_sorted_unique(bundled: Registry) -> None:
    ids = bundled.ids()
    assert ids == sorted(set(ids))
    assert "METRC_ACTIVE_ITEMS" in ids


# --------------------------------------------------------------------------- classification


def test_collection_via_allof_pagination() -> None:
    assert only(registry({"/v2/things": {"get": {"responses": ok_json(PAGINATED)}}})).kind == "collection"


def test_collection_via_direct_pagination_ref() -> None:
    schema = {"$ref": "#/components/schemas/Pagination"}
    assert only(registry({"/v2/things": {"get": {"responses": ok_json(schema)}}})).kind == "collection"


def test_collection_via_named_schema_and_response_refs() -> None:
    reg = registry(
        {"/v2/things": {"get": {"responses": {"200": {"$ref": "#/components/responses/ThingList"}}}}},
        components={
            "schemas": {"ThingPage": PAGINATED},
            "responses": {
                "ThingList": {
                    "description": "ok",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ThingPage"}}},
                }
            },
        },
    )
    assert only(reg).kind == "collection"


def test_paginated_schema_on_non_get_is_not_a_collection() -> None:
    ep = only(registry({"/v2/things": {"post": {"responses": ok_json(PAGINATED)}}}))
    assert ep.kind == "immediate_write"


@pytest.mark.parametrize(
    "responses",
    [
        ok_json({"type": "array"}),
        ok_json({"allOf": None}),
        ok_json({"allOf": ["not a mapping", {"$ref": "#/components/schemas/Other"}]}),
        ok_json({"$ref": "#/components/schemas/JustAString"}),
        {"200": {"description": "ok", "content": {"application/json": {}}}},
        {"200": {"description": "ok", "content": None}},
        {"200": {"description": "ok", "content": {"text/plain": {}}}},
        {"201": {"description": "created", "content": {"application/json": {"schema": PAGINATED}}}},
        None,
    ],
)
def test_get_without_pagination_is_other(responses: Any) -> None:
    reg = registry(
        {"/v2/things": {"get": {"responses": responses}}},
        components={"schemas": {"JustAString": "string", "Other": {"type": "object"}}},
    )
    assert only(reg).kind == "other"


@pytest.mark.parametrize("ctype", ["text/csv", XLSX])
def test_report_by_content_type(ctype: str) -> None:
    reg = registry({"/v2/things/report": {"get": {"responses": ok_content("application/json", ctype)}}})
    assert only(reg).kind == "report"


def test_report_rule_comes_before_write_rules() -> None:
    reg = registry({"/v2/things/export": {"post": {"responses": ok_content("text/csv")}}})
    assert only(reg).kind == "report"


def test_report_found_in_any_response() -> None:
    responses = {
        "200": {"description": "ok", "content": {"application/json": {}}},
        "202": {"description": "csv", "content": {"text/csv": {}}},
    }
    assert only(registry({"/v2/r": {"get": {"responses": responses}}})).kind == "report"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_metrc_write_has_submit_query_param(method: str) -> None:
    op = {"parameters": [{"name": "submit", "in": "query", "schema": {"type": "boolean"}}]}
    assert only(registry({"/v2/things": {method: op}})).kind == "metrc_write"


def test_submit_from_path_level_parameter_ref() -> None:
    reg = registry(
        {"/v2/things": {"parameters": [{"$ref": "#/components/parameters/Submit"}], "post": {}}},
        components={"parameters": {"Submit": {"name": "submit", "in": "query"}}},
    )
    assert only(reg).kind == "metrc_write"


def test_submit_header_is_not_a_metrc_write() -> None:
    op = {"parameters": [{"name": "submit", "in": "header"}]}
    assert only(registry({"/v2/things": {"post": op}})).kind == "immediate_write"


def test_immediate_write() -> None:
    assert only(registry({"/v2/things": {"delete": {}}})).kind == "immediate_write"


@pytest.mark.parametrize("ctype", ["application/pdf", "image/png", "image/jpeg"])
def test_file(ctype: str) -> None:
    assert only(registry({"/v2/doc/{object_id}": {"get": {"responses": ok_content(ctype)}}})).kind == "file"


def test_object() -> None:
    assert only(registry({"/v2/things/{object_id}": {"get": {}}})).kind == "object"


def test_other_path_param_name_is_not_object() -> None:
    assert only(registry({"/v2/things/{thing_id}": {"get": {}}})).kind == "other"


@pytest.mark.parametrize("method", ["head", "options"])
def test_head_and_options_are_other(method: str) -> None:
    reg = registry({"/v2/things/{object_id}": {method: {"responses": ok_content("application/pdf")}}})
    assert only(reg).kind == "other"


# --------------------------------------------------------------------------- building endpoints


def test_build_skips_non_operations() -> None:
    reg = registry(
        {
            "/v2/a": {"get": {}, "summary": "path summary", "parameters": [], "trace": {}, "post": "nope"},
            "/v2/b": "not a path item",
        }
    )
    assert [(ep.method, ep.path) for ep in reg.endpoints] == [("GET", "/v2/a")]


def test_empty_spec() -> None:
    reg = Registry({})
    assert reg.endpoints == []
    assert reg.version == ""
    assert reg.ids() == []
    assert reg.source is None


def test_source_and_version_kept() -> None:
    source = SpecSource("bundled", "api.test")
    reg = Registry({"info": {"version": "v9"}, "paths": {}}, source)
    assert reg.source is source
    assert reg.version == "v9"


def test_params_merge_resolve_and_defaults() -> None:
    reg = registry(
        {
            "/v2/things/{object_id}": {
                "parameters": [
                    {"name": "object_id", "in": "path"},
                    {"name": "licenseNumber", "in": "query", "description": "path-level"},
                    "not a mapping",
                    {"in": "query"},
                ],
                "get": {
                    "parameters": [
                        {"name": "licenseNumber", "in": "query", "required": True, "description": "op-level"},
                        {"$ref": "#/components/parameters/Filter"},
                        {"name": "loose"},
                        {"name": "weird", "in": "query", "schema": {"$ref": "#/components/schemas/JustAString"}},
                        {"name": "X-Thing", "in": "header", "schema": None},
                    ]
                },
            }
        },
        components={
            "parameters": {
                "Filter": {
                    "name": "filter",
                    "in": "query",
                    "schema": {"$ref": "#/components/schemas/FilterList"},
                }
            },
            "schemas": {"FilterList": {"type": "array", "items": {"type": "string"}}, "JustAString": "string"},
        },
    )
    ep = only(reg)
    names = [(p.location, p.name) for p in ep.params]
    assert names == [
        ("path", "object_id"),
        ("query", "licenseNumber"),
        ("query", "filter"),
        ("query", "loose"),
        ("query", "weird"),
        ("header", "X-Thing"),
    ]
    obj = ep.param("object_id")
    assert obj is not None and obj.required  # path params are always required
    lic = ep.param("licenseNumber")
    assert lic is not None and lic.required and lic.description == "op-level"
    flt = ep.param("filter")
    assert flt is not None and flt.is_array and flt.schema["items"] == {"type": "string"}
    loose = ep.param("loose")
    assert loose is not None and loose.location == "query" and not loose.required and not loose.is_array
    weird = ep.param("weird")
    assert weird is not None and weird.schema == {}
    assert ep.param("missing") is None
    assert [p.name for p in ep.path_params] == ["object_id"]
    assert [p.name for p in ep.query_params] == ["licenseNumber", "filter", "loose", "weird"]


def test_request_body_and_security() -> None:
    reg = registry(
        {
            "/v2/required": {"post": {"requestBody": {"$ref": "#/components/requestBodies/Thing"}}},
            "/v2/optional": {"post": {"requestBody": {"content": {"application/json": {}}}}},
            "/v2/none": {"post": {"security": []}},
        },
        components={"requestBodies": {"Thing": {"required": True, "content": {"application/json": {}}}}},
        security=[{"ApiKey": []}],
    )
    required = reg.endpoint("/v2/required")
    assert required.has_body and required.body_required and not required.public
    optional = reg.endpoint("/v2/optional")
    assert optional.has_body and not optional.body_required
    none = reg.endpoint("/v2/none")
    assert not none.has_body and not none.body_required
    assert none.public


def test_global_empty_security_makes_everything_public() -> None:
    reg = registry({"/v2/a": {"get": {}}, "/v2/b": {"get": {"security": [{"ApiKey": []}]}}}, security=[])
    assert reg.endpoint("/v2/a").public
    assert not reg.endpoint("/v2/b").public


def test_no_security_anywhere_is_not_public() -> None:
    assert not only(registry({"/v2/a": {"get": {}}})).public


def test_summary_suffix_stripping() -> None:
    reg = registry(
        {
            "/v2/a": {"get": {"x-t3-endpoint-id": "A_ID", "summary": "  List of A · A_ID  "}},
            "/v2/b": {"get": {"x-t3-endpoint-id": "B_ID", "summary": "List of B · OTHER", "tags": ["Bees", 7]}},
            "/v2/c": {"get": {"summary": "No id · C_ID"}},
            "/v2/d": {"get": {"x-t3-endpoint-id": "D_ID"}},
        }
    )
    assert reg.endpoint("A_ID").summary == "List of A"
    b = reg.endpoint("B_ID")
    assert b.summary == "List of B · OTHER"
    assert b.tags == ("Bees", "7")
    c = reg.endpoint("/v2/c")
    assert c.id is None and c.summary == "No id · C_ID"
    assert reg.endpoint("D_ID").summary == ""


def test_endpoint_label_and_str() -> None:
    reg = registry({"/v2/a": {"get": {"x-t3-endpoint-id": "A_ID"}}, "/v2/b": {"delete": {}}})
    a = reg.endpoint("A_ID")
    assert a.label() == "GET /v2/a (A_ID)"
    assert str(a) == "GET /v2/a (A_ID)"
    b = reg.endpoint("/v2/b")
    assert b.label() == "DELETE /v2/b"
    assert b.is_write


def test_param_is_array() -> None:
    assert Param("f", "query", schema={"type": "array"}).is_array
    assert not Param("f", "query").is_array


# --------------------------------------------------------------------------- $ref resolution


def test_resolver_follows_refs_and_escapes() -> None:
    spec: dict[str, Any] = {
        "components": {"schemas": {"a/b": {"type": "slash"}, "c~d": {"type": "tilde"}, "Alias": {"$ref": "#/components/schemas/a~1b"}}}
    }
    r = _Resolver(spec)
    assert r.deref({"$ref": "#/components/schemas/a~1b"}) == {"type": "slash"}
    assert r.deref({"$ref": "#/components/schemas/c~0d"}) == {"type": "tilde"}
    assert r.deref({"$ref": "#/components/schemas/Alias"}) == {"type": "slash"}
    assert r.deref({"type": "plain"}) == {"type": "plain"}
    assert r.deref("scalar") == "scalar"


@pytest.mark.parametrize(
    "node",
    [
        {"$ref": "other.json#/components/schemas/X"},
        {"$ref": 12},
        {"$ref": "#/components/schemas/Missing"},
        {"$ref": "#/components/schemas/Leaf/deeper"},
    ],
)
def test_resolver_leaves_unresolvable_refs(node: dict[str, Any]) -> None:
    r = _Resolver({"components": {"schemas": {"Leaf": "string"}}})
    assert r.deref(node) is node


def test_resolver_stops_on_cycles() -> None:
    spec: dict[str, Any] = {
        "components": {"schemas": {"A": {"$ref": "#/components/schemas/B"}, "B": {"$ref": "#/components/schemas/A"}}}
    }
    result = _Resolver(spec).deref({"$ref": "#/components/schemas/A"})
    assert "$ref" in result


def test_cyclic_refs_do_not_break_registry() -> None:
    reg = registry(
        {"/v2/loop": {"get": {"parameters": [{"$ref": "#/components/parameters/P1"}], "responses": ok_json({"$ref": "#/components/schemas/S1"})}}},
        components={
            "parameters": {"P1": {"$ref": "#/components/parameters/P2"}, "P2": {"$ref": "#/components/parameters/P1"}},
            "schemas": {"S1": {"$ref": "#/components/schemas/S2"}, "S2": {"$ref": "#/components/schemas/S1"}},
        },
    )
    ep = only(reg)
    assert ep.kind == "other"
    assert ep.params == ()


# --------------------------------------------------------------------------- lookup

def path_param(*names: str) -> list[dict[str, Any]]:
    return [{"name": n, "in": "path", "required": True} for n in names]


LOOKUP_PATHS: dict[str, Any] = {
    "/v2/things": {
        "get": {"x-t3-endpoint-id": "THINGS", "responses": ok_json(PAGINATED), "summary": "List things", "tags": ["Things"]},
        "post": {"x-t3-endpoint-id": "THINGS_CREATE", "parameters": [{"name": "submit", "in": "query"}]},
    },
    "/v2/things/{object_id}": {"parameters": path_param("object_id"), "get": {"x-t3-endpoint-id": "THINGS"}},
    "/v2/things/report": {"get": {"x-t3-endpoint-id": "THINGS", "responses": ok_content("text/csv")}},
    "/v2/pair/{a}": {"get": {"x-t3-endpoint-id": "PAIR", "parameters": path_param("a")}},
    "/v2/pair/{a}/x/{b}": {"get": {"x-t3-endpoint-id": "PAIR", "parameters": path_param("a", "b")}},
    "/v2/twin/{a}": {"get": {"x-t3-endpoint-id": "TWIN", "parameters": path_param("a")}},
    "/v2/twin/{a}/same": {"get": {"x-t3-endpoint-id": "TWIN", "parameters": path_param("a")}},
    "/v2/dup-a": {"get": {"x-t3-endpoint-id": "DUP"}},
    "/v2/dup-b": {"get": {"x-t3-endpoint-id": "DUP"}},
    "/": {"get": {"summary": "root"}},
}


@pytest.fixture
def lookup() -> Registry:
    return registry(LOOKUP_PATHS)


def test_id_with_several_operations_picked_by_kind(lookup: Registry) -> None:
    assert lookup.endpoint("THINGS", kind="collection").path == "/v2/things"
    assert lookup.endpoint("THINGS", kind="report").path == "/v2/things/report"
    assert lookup.endpoint("THINGS", kind="object").path == "/v2/things/{object_id}"
    assert lookup.endpoint("THINGS", kind=["object", "report"], path_params=["object_id"]).kind == "object"


def test_id_picked_by_method(lookup: Registry) -> None:
    assert lookup.endpoint("/v2/things", method="post").kind == "metrc_write"
    assert lookup.endpoint("/v2/things", method="GET").kind == "collection"


def test_without_hints_the_route_needing_no_path_params_wins(lookup: Registry) -> None:
    # Two routes need no path params (collection and report), so it's ambiguous...
    with pytest.raises(SpecError, match="matches more than one operation") as info:
        lookup.endpoint("THINGS")
    message = str(info.value)
    assert "GET /v2/things (THINGS) [collection]" in message
    assert "GET /v2/things/report (THINGS) [report]" in message
    assert "/v2/things/{object_id}" not in message
    # ...but a path param name picks the object route.
    assert lookup.endpoint("THINGS", path_params=["object_id"]).kind == "object"


def test_most_specific_fillable_route_wins(lookup: Registry) -> None:
    assert lookup.endpoint("PAIR", path_params=["a"]).path == "/v2/pair/{a}"
    assert lookup.endpoint("PAIR", path_params=["a", "b"]).path == "/v2/pair/{a}/x/{b}"


def test_ambiguous_when_nothing_is_fillable(lookup: Registry) -> None:
    with pytest.raises(SpecError, match="matches more than one operation") as info:
        lookup.endpoint("PAIR")
    assert "/v2/pair/{a}/x/{b}" in str(info.value)
    assert "Pass a path" in str(info.value)


def test_ambiguous_when_fillable_routes_tie(lookup: Registry) -> None:
    with pytest.raises(SpecError, match="matches more than one operation") as info:
        lookup.endpoint("TWIN", path_params=["a"])
    assert "/v2/twin/{a}/same" in str(info.value)
    with pytest.raises(SpecError):
        lookup.endpoint("DUP")


def test_no_operation_of_the_wanted_method_or_kind(lookup: Registry) -> None:
    with pytest.raises(SpecError) as by_method:
        lookup.endpoint("/v2/things", method="delete")
    assert "has no DELETE operation" in str(by_method.value)
    assert "GET /v2/things (THINGS) [collection]" in str(by_method.value)
    with pytest.raises(SpecError) as by_kind:
        lookup.endpoint("THINGS", kind=["file", "other"])
    assert "has no file/other operation" in str(by_kind.value)
    with pytest.raises(SpecError) as both:
        lookup.endpoint("/v2/things", method="get", kind="report")
    assert "has no GET report operation" in str(both.value)
    assert not isinstance(both.value, UnknownEndpoint)


def test_paths_with_query_and_trailing_slash(lookup: Registry) -> None:
    assert lookup.endpoint("/v2/things/?licenseNumber=X", method="GET").path == "/v2/things"
    assert lookup.endpoint("/v2/things/42/").path == "/v2/things/{object_id}"
    assert lookup.endpoint("/").path == "/"


def test_candidates(lookup: Registry) -> None:
    assert [ep.path for ep in lookup.candidates("/v2/pair/1/x/2")] == ["/v2/pair/{a}/x/{b}"]
    assert lookup.candidates("/v2/nothing/here") == []
    assert lookup.candidates("not-an-id-or-path") == []
    # Lists are copies: changing one doesn't change the registry.
    lookup.candidates("THINGS").clear()
    assert len(lookup.candidates("THINGS")) == 3


def test_unknown_suggestions(lookup: Registry) -> None:
    with pytest.raises(UnknownEndpoint) as close:
        lookup.endpoint("THINGZ")
    assert close.value.suggestions[0] == "THINGS"
    with pytest.raises(UnknownEndpoint) as substring:
        lookup.endpoint("create")
    assert substring.value.suggestions == ["THINGS_CREATE"]
    with pytest.raises(UnknownEndpoint) as by_path:
        lookup.endpoint("/v2/thingz")
    assert "/v2/things" in by_path.value.suggestions
    with pytest.raises(UnknownEndpoint) as nothing:
        lookup.endpoint("/zzzzzzzzzzzzzz/qqqqqqq")
    assert nothing.value.suggestions == []
    with pytest.raises(UnknownEndpoint) as nothing_id:
        lookup.endpoint("QQQQQQQQ")
    assert nothing_id.value.suggestions == []


def test_find(lookup: Registry) -> None:
    assert [ep.path for ep in lookup.find("list things")] == ["/v2/things"]
    assert {ep.id for ep in lookup.find("THINGS")} == {"THINGS", "THINGS_CREATE"}
    assert [ep.path for ep in lookup.find("things", kind="report")] == ["/v2/things/report"]
    assert len(lookup.find()) == len(lookup.endpoints)
    assert lookup.find("things nonexistent-word") == []
    assert lookup.find("ROOT")[0].path == "/"


def test_list_rejects_unknown_kind(lookup: Registry) -> None:
    with pytest.raises(ValueError, match="kind must be one of collection, report"):
        lookup.list("bogus")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        lookup.find("x", kind="bogus")  # type: ignore[arg-type]


def test_ids(lookup: Registry) -> None:
    assert lookup.ids() == ["DUP", "PAIR", "THINGS", "THINGS_CREATE", "TWIN"]


# --------------------------------------------------------------------------- check_params


@pytest.fixture
def checked() -> Registry:
    return registry(
        {
            "/v2/things/{object_id}": {
                "post": {
                    "parameters": [
                        {"name": "object_id", "in": "path"},
                        {"name": "licenseNumber", "in": "query", "required": True},
                        {"name": "mode", "in": "query", "required": True},
                        {"name": "page", "in": "query", "required": True},
                        {"name": "submit", "in": "query", "required": True},
                        {"name": "secretKey", "in": "query", "required": True},
                        {"name": "X-Req", "in": "header", "required": True},
                        {"name": "sort", "in": "query"},
                    ],
                    "requestBody": {"required": True, "content": {"application/json": {}}},
                }
            }
        }
    )


def test_check_params_passes_when_complete(checked: Registry, caplog: pytest.LogCaptureFixture) -> None:
    ep = checked.endpoints[0]
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        checked.check_params(
            ep, {"licenseNumber": "L", "mode": "x", "sort": "a", "page": 2}, {"object_id": 5}, has_body=True
        )
    assert caplog.records == []


@pytest.mark.parametrize("empty", [None, ""])
def test_check_params_missing_path_param(checked: Registry, empty: Any) -> None:
    ep = checked.endpoints[0]
    with pytest.raises(SpecError, match=r"needs: object_id= \(path\)\."):
        checked.check_params(ep, {"licenseNumber": "L", "mode": "x"}, {"object_id": empty}, has_body=True)


@pytest.mark.parametrize("empty", [None, "", []])
def test_check_params_missing_query_uses_python_name(checked: Registry, empty: Any) -> None:
    ep = checked.endpoints[0]
    with pytest.raises(SpecError) as info:
        checked.check_params(
            ep,
            {"licenseNumber": empty},
            {},
            has_body=True,
            python_names={"licenseNumber": "license"},
        )
    message = str(info.value)
    assert message == "POST /v2/things/{object_id} needs: object_id= (path), license=, mode (query)."
    # Managed params (page, submit, secretKey) and header params are never reported.
    assert "page" not in message and "submit" not in message and "secretKey" not in message
    assert "X-Req" not in message


def test_check_params_missing_body(checked: Registry) -> None:
    ep = checked.endpoints[0]
    with pytest.raises(SpecError, match=r"needs a request body \(json=\.\.\.\)"):
        checked.check_params(ep, {"licenseNumber": "L", "mode": "x"}, {"object_id": 1}, has_body=False)


def test_check_params_warns_about_unknown_query_params(
    checked: Registry, caplog: pytest.LogCaptureFixture
) -> None:
    ep = checked.endpoints[0]
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        checked.check_params(
            ep,
            {"licenseNumber": "L", "mode": "x", "zeta": 1, "alpha": 2, "submit": "true", "secretKey": "s"},
            {"object_id": 1},
            has_body=True,
        )
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert record.getMessage() == (
        "POST /v2/things/{object_id} doesn't list query parameter(s) alpha, zeta in the spec; sending anyway."
    )


def test_check_params_optional_body_not_required() -> None:
    reg = registry({"/v2/x": {"post": {}}})
    reg.check_params(reg.endpoints[0], {}, {}, has_body=False)


def test_check_params_bundled(bundled: Registry) -> None:
    ep = bundled.endpoint("METRC_ACTIVE_ITEMS", kind="object")
    with pytest.raises(SpecError, match="object_id"):
        bundled.check_params(ep, {"licenseNumber": "L"}, {}, has_body=False)
    discontinue = bundled.endpoint("/v2/items/discontinue")
    with pytest.raises(SpecError, match="request body"):
        bundled.check_params(discontinue, {"licenseNumber": "L"}, {}, has_body=False)


# --------------------------------------------------------------------------- request body shape


@pytest.mark.parametrize(
    ("path", "method", "body_type"),
    [
        ("/v2/packages/change-locations", "POST", "array"),
        ("/v2/packages/adjust", "POST", "array"),
        ("/v2/items/create", "POST", "array"),
        ("/v2/strains/create", "POST", "array"),
        ("/v2/items/discontinue", "POST", "object"),
        ("/v2/transfers/void", "POST", "object"),
        ("/v2/tag-lists", "POST", "object"),
        ("/v2/items/images/file", "POST", None),  # multipart
        ("/v2/auth/logout", "POST", None),  # no body
        ("/v2/items", "GET", None),
    ],
)
def test_bundled_body_types(bundled: Registry, path: str, method: str, body_type: str | None) -> None:
    ep = bundled.endpoint(path, method=method)
    assert ep.body_type == body_type
    assert ep.body_is_array is (body_type == "array")


def write_op(content: dict[str, Any]) -> dict[str, Any]:
    return {"post": {"requestBody": {"content": content}, "responses": {"200": {"description": "ok"}}}}


def test_body_type_follows_refs_and_skips_non_json_content() -> None:
    reg = registry(
        {"/v2/x": write_op({"text/plain": {}, "application/json": {"schema": {"$ref": "#/components/schemas/Rows"}}})},
        components={"schemas": {"Rows": {"type": "array", "items": {"type": "object"}}}},
    )
    assert only(reg).body_type == "array"


@pytest.mark.parametrize(
    "content",
    [
        {"application/json": {"schema": {"oneOf": [{"type": "object"}, {"type": "array"}]}}},
        {"application/json": {}},
        {"application/json": "not a media object"},
        {"application/json": {"schema": {"$ref": "#/components/schemas/Missing"}}},
        {"multipart/form-data": {"schema": {"type": "object"}}},
    ],
)
def test_body_type_is_none_when_unclear(content: dict[str, Any]) -> None:
    assert only(registry({"/v2/x": write_op(content)})).body_type is None


def test_param_choices() -> None:
    array_enum = Param("include", "query", schema={"type": "array", "items": {"type": "string", "enum": ["a", "b"]}})
    plain_enum = Param("kind", "query", schema={"type": "string", "enum": ["x", 1]})
    array_no_enum = Param("ids", "query", schema={"type": "array", "items": {"type": "string"}})
    array_no_items = Param("ids", "query", schema={"type": "array"})
    plain = Param("name", "query", schema={"type": "string"})
    assert array_enum.choices == ("a", "b")
    assert plain_enum.choices == ("x", "1")
    assert array_no_enum.choices == array_no_items.choices == plain.choices == ()


def test_bundled_super_collection_includes(bundled: Registry) -> None:
    param = bundled.endpoint("METRC_ACTIVE_SUPERITEMS", kind="collection").param("include")
    assert param is not None
    assert {"notes", "history", "ingredients", "images"} <= set(param.choices)
