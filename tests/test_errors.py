"""errors.py: the exception hierarchy and error_from_response()."""

from __future__ import annotations

from typing import Any

import httpx2
import pytest

from t3api_utils.errors import (
    APIError,
    AuthError,
    AuthRequired,
    NotFound,
    NotInteractive,
    RateLimited,
    ServerError,
    SpecError,
    T3Error,
    TagListResolveError,
    UnknownEndpoint,
    ValidationError,
    error_from_response,
)

BASE = "https://api.test"


def make_response(
    status: int,
    *,
    method: str = "GET",
    path: str = "/v2/items",
    json: Any = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> httpx2.Response:
    request = httpx2.Request(method, BASE + path)
    if content is not None:
        return httpx2.Response(status, content=content, headers=headers, request=request)
    if json is not None:
        return httpx2.Response(status, json=json, headers=headers, request=request)
    return httpx2.Response(status, headers=headers, request=request)


# --------------------------------------------------------------------------- hierarchy


def test_hierarchy() -> None:
    for cls in (AuthRequired, NotInteractive, SpecError, APIError):
        assert issubclass(cls, T3Error)
    assert issubclass(UnknownEndpoint, SpecError)
    for cls in (AuthError, NotFound, ValidationError, RateLimited, ServerError):
        assert issubclass(cls, APIError)
    assert issubclass(TagListResolveError, ValidationError)


def test_unknown_endpoint_with_suggestions() -> None:
    exc = UnknownEndpoint("METRC_ACTIVE_ITEM", ["METRC_ACTIVE_ITEMS", "METRC_INACTIVE_ITEMS"])
    assert exc.name == "METRC_ACTIVE_ITEM"
    assert exc.suggestions == ["METRC_ACTIVE_ITEMS", "METRC_INACTIVE_ITEMS"]
    text = str(exc)
    assert "'METRC_ACTIVE_ITEM' is not in the T3 OpenAPI spec." in text
    assert "Close matches: METRC_ACTIVE_ITEMS, METRC_INACTIVE_ITEMS." in text
    assert "client.spec.find" in text
    assert "client.http" in text


def test_unknown_endpoint_without_suggestions() -> None:
    exc = UnknownEndpoint("/v2/nope")
    assert exc.suggestions == []
    assert "Close matches" not in str(exc)
    assert str(exc).startswith("'/v2/nope' is not in the T3 OpenAPI spec.")


def test_api_error_keeps_response_and_appends_hint() -> None:
    response = make_response(418, method="POST", path="/v2/x")
    exc = APIError("boom", response=response, detail="d", errors=[1], code="C", hint="do this")
    assert exc.response is response
    assert exc.status_code == 418
    assert exc.method == "POST"
    assert exc.url == BASE + "/v2/x"
    assert exc.detail == "d"
    assert exc.errors == [1]
    assert exc.code == "C"
    assert exc.hint == "do this"
    assert str(exc) == "boom\ndo this"


def test_api_error_without_hint() -> None:
    exc = APIError("boom", response=make_response(418))
    assert str(exc) == "boom"
    assert exc.errors == []
    assert exc.detail is None and exc.code is None and exc.hint is None


# --------------------------------------------------------------------------- status -> class


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, ValidationError),
        (401, AuthError),
        (403, AuthError),
        (404, NotFound),
        (409, APIError),
        (422, ValidationError),
        (429, RateLimited),
        (500, ServerError),
        (502, ServerError),
        (503, ServerError),
    ],
)
def test_status_maps_to_subclass(status: int, cls: type[APIError]) -> None:
    exc = error_from_response(make_response(status, json={"detail": "nope"}))
    assert type(exc) is cls
    assert exc.status_code == status
    assert exc.detail == "nope"


def test_other_status_is_plain_api_error_and_empty_reason_is_tidy() -> None:
    exc = error_from_response(make_response(499, json={"detail": "odd"}))
    assert type(exc) is APIError
    # 499 has no reason phrase; there's no double space in the message.
    assert str(exc) == "499 from GET /v2/items: odd"


def test_message_includes_reason_method_path_and_detail() -> None:
    exc = error_from_response(make_response(404, path="/v2/items/1", json={"detail": "Item not found"}))
    assert str(exc) == "404 Not Found from GET /v2/items/1: Item not found"
    assert exc.hint is None


def test_message_without_detail() -> None:
    exc = error_from_response(make_response(500, content=b""))
    assert exc.detail is None
    assert str(exc) == "500 Internal Server Error from GET /v2/items"


def test_rate_limited_has_hint() -> None:
    exc = error_from_response(make_response(429, json={"detail": "slow down"}))
    assert isinstance(exc, RateLimited)
    assert exc.hint is not None and "rate_limit=" in exc.hint
    assert exc.hint in str(exc)


# --------------------------------------------------------------------------- 401/403 hints


def test_403_hint_mentions_access_whatever_the_credential() -> None:
    for kind in ("secret_key", "jwt", None):
        exc = error_from_response(make_response(403, json={"detail": "x"}), credential_kind=kind)
        assert isinstance(exc, AuthError)
        assert exc.hint is not None and "doesn't have access" in exc.hint


def test_401_secret_key_metrc_login_failure() -> None:
    response = make_response(401, json={"detail": "Metrc login failed", "code": "METRC_LOGIN_FAILURE"})
    exc = error_from_response(response, credential_kind="secret_key")
    assert isinstance(exc, AuthError)
    assert exc.code == "METRC_LOGIN_FAILURE"
    assert exc.hint is not None
    assert "Metrc credentials behind this secret key have changed" in exc.hint
    assert "t3api keys rotate" in exc.hint


def test_401_secret_key_other() -> None:
    exc = error_from_response(make_response(401, json={"detail": "bad"}), credential_kind="secret_key")
    assert exc.hint is not None
    assert "secret key was rejected" in exc.hint
    assert "t3api login" in exc.hint


def test_401_jwt() -> None:
    exc = error_from_response(make_response(401, json={"detail": "expired"}), credential_kind="jwt")
    assert exc.hint is not None and "JWT has expired" in exc.hint


def test_401_no_credential() -> None:
    exc = error_from_response(make_response(401, json={"detail": "who?"}))
    assert exc.hint is not None and "T3_SECRET_KEY" in exc.hint


# --------------------------------------------------------------------------- tag-list resolve


def test_422_with_tag_list_code_is_tag_list_resolve_error() -> None:
    errors = [{"handle": "ABC", "reason": "NOT_FOUND", "matchCount": 0}]
    response = make_response(
        422,
        path="/v2/somewhere",
        json={"title": "Unresolved", "code": "TAG_LIST_UNRESOLVED_ENTRIES", "errors": errors},
    )
    exc = error_from_response(response)
    assert type(exc) is TagListResolveError
    assert exc.errors == errors
    assert exc.detail == "Unresolved"


def test_422_on_resolve_path_is_tag_list_resolve_error() -> None:
    response = make_response(422, path="/v2/tag-lists/42/resolve", json={"detail": "2 handles failed"})
    assert type(error_from_response(response)) is TagListResolveError


def test_422_elsewhere_is_plain_validation_error() -> None:
    assert type(error_from_response(make_response(422, path="/v2/tag-lists/42", json={"detail": "x"}))) is (
        ValidationError
    )
    assert type(error_from_response(make_response(422, path="/v2/other/resolve", json={"detail": "x"}))) is (
        ValidationError
    )


def test_400_with_tag_list_code_stays_validation_error() -> None:
    response = make_response(400, json={"detail": "x", "code": "TAG_LIST_UNRESOLVED_ENTRIES"})
    assert type(error_from_response(response)) is ValidationError


# --------------------------------------------------------------------------- body parsing


def test_problem_json_detail_errors_and_code() -> None:
    body = {
        "type": "about:blank",
        "title": "Bad Request",
        "detail": "name is required",
        "errors": [{"field": "name"}],
        "code": "VALIDATION",
    }
    exc = error_from_response(
        make_response(400, json=body, headers={"content-type": "application/problem+json"})
    )
    assert exc.detail == "name is required"
    assert exc.errors == [{"field": "name"}]
    assert exc.code == "VALIDATION"


def test_title_used_when_no_detail() -> None:
    assert error_from_response(make_response(400, json={"title": "Bad Request"})).detail == "Bad Request"


def test_non_list_errors_and_non_string_code_are_ignored() -> None:
    exc = error_from_response(make_response(400, json={"detail": "x", "errors": {"a": 1}, "code": 7}))
    assert exc.errors == []
    assert exc.code is None


def test_t3_nested_error_message() -> None:
    body = {"error": {"type": "VALIDATION", "message": "Item 5 is not active", "code": "INACTIVE"}}
    exc = error_from_response(make_response(400, json=body))
    assert exc.detail == "Item 5 is not active"
    assert exc.code == "INACTIVE"


def test_t3_nested_error_type_when_no_message() -> None:
    exc = error_from_response(make_response(400, json={"error": {"type": "VALIDATION"}}))
    assert exc.detail == "VALIDATION"
    assert exc.code is None


def test_t3_nested_error_code_does_not_override_top_level_code() -> None:
    body = {"code": "TOP", "error": {"message": "m", "code": "NESTED"}}
    assert error_from_response(make_response(400, json=body)).code == "TOP"


def test_t3_nested_error_non_string_code_ignored() -> None:
    body = {"error": {"message": "m", "code": 12}}
    assert error_from_response(make_response(400, json=body)).code is None


def test_nested_error_without_message_or_type_falls_back_to_json() -> None:
    body = {"error": {"other": 1}}
    exc = error_from_response(make_response(400, json=body))
    assert exc.detail == '{"error": {"other": 1}}'


def test_string_error() -> None:
    assert error_from_response(make_response(400, json={"error": "Bad thing"})).detail == "Bad thing"


def test_message_field() -> None:
    assert error_from_response(make_response(400, json={"message": "Nope"})).detail == "Nope"


def test_unknown_dict_shape_is_dumped() -> None:
    exc = error_from_response(make_response(400, json={"weird": [1, 2]}))
    assert exc.detail == '{"weird": [1, 2]}'


def test_dumped_body_is_truncated() -> None:
    exc = error_from_response(make_response(400, json={"weird": "x" * 2000}))
    assert exc.detail is not None and len(exc.detail) == 500


def test_non_dict_json_body() -> None:
    exc = error_from_response(make_response(400, json=["a", "b"]))
    assert exc.detail == '["a", "b"]'
    assert exc.errors == [] and exc.code is None


def test_non_json_text_body() -> None:
    exc = error_from_response(make_response(502, content=b"  <html>Bad Gateway</html>  "))
    assert exc.detail == "<html>Bad Gateway</html>"
    assert isinstance(exc, ServerError)


def test_long_text_body_is_truncated() -> None:
    exc = error_from_response(make_response(500, content=b"y" * 2000))
    assert exc.detail == "y" * 500 + "…"


def test_invalid_utf8_body_does_not_crash() -> None:
    exc = error_from_response(make_response(500, content=b"\xff\xfe\xfa not json"))
    assert exc.detail is not None and "not json" in exc.detail


# --------------------------------------------------------------------------- redaction


def test_secret_key_path_is_redacted() -> None:
    response = make_response(401, method="PUT", path="/v2/auth/secretkey/abcd-1234", json={"detail": "x"})
    exc = error_from_response(response, credential_kind="secret_key")
    assert "abcd-1234" not in str(exc)
    assert "abcd-1234" not in exc.url
    assert "/v2/auth/secretkey/***" in str(exc)
    assert exc.url == BASE + "/v2/auth/secretkey/***"


def test_secret_key_query_is_redacted_in_url() -> None:
    request = httpx2.Request("GET", BASE + "/v2/items/report?licenseNumber=L&secretKey=sk-123")
    response = httpx2.Response(404, json={"detail": "x"}, request=request)
    exc = error_from_response(response)
    assert "sk-123" not in exc.url
    assert "secretKey=***" in exc.url
    assert exc.response is response
