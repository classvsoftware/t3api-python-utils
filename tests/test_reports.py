"""client.report() and client.report_url()."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from t3api_utils._http import REPORT_TIMEOUT
from t3api_utils.auth.credentials import BearerAuth, SecretKeyAuth
from t3api_utils.client import T3Client
from t3api_utils.errors import SpecError, T3Error, ValidationError
from tests.conftest import Router

REPORT = "/v2/items/report"
CSV = b"name,productCategoryName\nBlue Dream,Buds\n"
SHEET = "https://docs.google.com/spreadsheets/d/abc"
URL_WARNING = "This report URL contains your secret key"


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
def csv_report(router: Router) -> Router:
    router.add("GET", REPORT, content=CSV, headers={"content-type": "text/csv"})
    return router


def params_of(router: Router) -> httpx2.QueryParams:
    return router.calls[-1].url.params


# --------------------------------------------------------------------------- licenses


def test_report_with_one_license(client: T3Client, csv_report: Router) -> None:
    assert client.report("ITEMS_REPORT", licenses="LIC-1") == CSV
    request = csv_report.calls[0]
    assert request.url.path == REPORT
    assert request.url.params.get_list("licenseNumber") == ["LIC-1"]
    assert request.url.params["contentType"] == "csv"
    assert request.extensions["timeout"]["read"] == REPORT_TIMEOUT


def test_report_by_path_with_several_licenses(client: T3Client, csv_report: Router) -> None:
    client.report(REPORT, licenses=["LIC-1", "LIC-2"])
    assert params_of(csv_report).get_list("licenseNumber") == ["LIC-1", "LIC-2"]


def test_report_license_defaults_to_client_license(router: Router, csv_report: Router) -> None:
    with make_client(router, license="LIC-9") as c:
        c.report("ITEMS_REPORT")
    assert params_of(router).get_list("licenseNumber") == ["LIC-9"]


def test_report_without_license_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="licenses="):
        client.report("ITEMS_REPORT")
    assert router.calls == []


def test_report_empty_license_list_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="empty"):
        client.report("ITEMS_REPORT", licenses=[])
    assert router.calls == []


def test_report_more_than_20_licenses_raises(client: T3Client, router: Router) -> None:
    licenses = [f"LIC-{i}" for i in range(21)]
    with pytest.raises(ValueError, match="at most 20"):
        client.report("ITEMS_REPORT", licenses=licenses)
    assert router.calls == []


def test_report_20_licenses_is_allowed(client: T3Client, csv_report: Router) -> None:
    licenses = [f"LIC-{i}" for i in range(20)]
    client.report("ITEMS_REPORT", licenses=licenses)
    assert params_of(csv_report).get_list("licenseNumber") == licenses


# --------------------------------------------------------------------------- query parameters


def test_report_query_parameters(client: T3Client, csv_report: Router) -> None:
    client.report(
        "ITEMS_REPORT",
        licenses="LIC-1",
        format="csv",
        columns=["name", "productCategoryName"],
        filter=["name__contains:flower", "id__gt:1"],
        filter_logic="or",
        sort="name:asc",
        row_limit=50,
        params={"prependCsvMetadata": "false"},
    )
    params = params_of(csv_report)
    assert params["columns"] == "name,productCategoryName"
    assert params.get_list("filter") == ["name__contains:flower", "id__gt:1"]
    assert params["filterLogic"] == "or"
    assert params["sort"] == "name:asc"
    assert params["rowLimit"] == "50"
    assert params["prependCsvMetadata"] == "false"
    assert "delivery" not in params
    assert "email" not in params


def test_report_string_columns_and_filter(client: T3Client, csv_report: Router) -> None:
    client.report("ITEMS_REPORT", licenses="LIC-1", columns="name", filter="name__eq:x")
    params = params_of(csv_report)
    assert params["columns"] == "name"
    assert params.get_list("filter") == ["name__eq:x"]


def test_report_minimal_query(client: T3Client, csv_report: Router) -> None:
    client.report("ITEMS_REPORT", licenses="LIC-1")
    assert set(params_of(csv_report).keys()) == {"licenseNumber", "contentType"}


def test_report_invalid_format_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="format must be one of"):
        client.report("ITEMS_REPORT", licenses="LIC-1", format="pdf")
    assert router.calls == []


def test_report_on_a_non_report_endpoint_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError):
        client.report("METRC_ACTIVE_ITEMS", licenses="LIC-1")
    assert router.calls == []


# --------------------------------------------------------------------------- return values


def test_report_json_is_parsed(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, json={"data": [{"name": "Blue Dream"}]})
    assert client.report("ITEMS_REPORT", licenses="LIC-1", format="json") == {
        "data": [{"name": "Blue Dream"}]
    }
    assert params_of(router)["contentType"] == "json"


def test_report_xlsx_is_bytes(client: T3Client, router: Router) -> None:
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    router.add("GET", REPORT, content=b"PK\x03\x04", headers={"content-type": xlsx})
    assert client.report("ITEMS_REPORT", licenses="LIC-1", format="xlsx") == b"PK\x03\x04"


def test_report_error_status_raises(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, status=400, json={"detail": "Invalid columns"})
    with pytest.raises(ValidationError, match="Invalid columns"):
        client.report("ITEMS_REPORT", licenses="LIC-1")


# --------------------------------------------------------------------------- to=


def test_report_to_file_streams_and_returns_path(client: T3Client, csv_report: Router, tmp_path: Path) -> None:
    target = tmp_path / "out" / "items.csv"
    assert client.report("ITEMS_REPORT", licenses="LIC-1", to=target) == target
    assert target.read_bytes() == CSV
    assert params_of(csv_report)["contentType"] == "csv"
    assert csv_report.calls[0].extensions["timeout"]["read"] == REPORT_TIMEOUT
    assert sorted(p.name for p in target.parent.iterdir()) == ["items.csv"]


def test_report_to_string_path(client: T3Client, csv_report: Router) -> None:
    result = client.report("ITEMS_REPORT", licenses="LIC-1", to="items.csv")
    assert result == Path("items.csv")
    assert Path("items.csv").read_bytes() == CSV


@pytest.mark.parametrize(
    ("name", "expected"),
    [("items.xlsx", "xlsx"), ("items.JSON", "json"), ("items.csv", "csv"), ("items.txt", "csv"), ("items", "csv")],
)
def test_report_format_inferred_from_suffix(
    client: T3Client, csv_report: Router, tmp_path: Path, name: str, expected: str
) -> None:
    client.report("ITEMS_REPORT", licenses="LIC-1", to=tmp_path / name)
    assert params_of(csv_report)["contentType"] == expected


def test_report_explicit_format_beats_suffix(client: T3Client, csv_report: Router, tmp_path: Path) -> None:
    client.report("ITEMS_REPORT", licenses="LIC-1", to=tmp_path / "items.csv", format="xlsx")
    assert params_of(csv_report)["contentType"] == "xlsx"


def test_report_to_file_error_status_leaves_no_file(client: T3Client, router: Router, tmp_path: Path) -> None:
    router.add("GET", REPORT, status=400, json={"detail": "Report Request Too Large"})
    target = tmp_path / "reports" / "items.csv"
    with pytest.raises(ValidationError) as info:
        client.report("ITEMS_REPORT", licenses="LIC-1", to=target)
    assert info.value.detail == "Report Request Too Large"
    assert info.value.response.status_code == 400
    assert list(target.parent.iterdir()) == []


class BrokenStream(httpx2.SyncByteStream):
    """Sends part of a body, then the connection drops."""

    def __iter__(self) -> Iterator[bytes]:
        yield b"name,productCategoryName\n"
        raise httpx2.ReadError("connection dropped")


def test_report_to_file_is_atomic(client: T3Client, router: Router, tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/csv"}, stream=BrokenStream())

    router.add("GET", REPORT, handler=handler)
    target = tmp_path / "reports" / "items.csv"
    target.parent.mkdir()
    target.write_bytes(b"previous report")
    with pytest.raises(httpx2.ReadError):
        client.report("ITEMS_REPORT", licenses="LIC-1", to=target)
    # The old file is untouched and no partial download is left behind.
    assert target.read_bytes() == b"previous report"
    assert [p.name for p in target.parent.iterdir()] == ["items.csv"]


# --------------------------------------------------------------------------- googleSheets


def test_google_sheets_returns_location(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, status=302, headers={"Location": SHEET}, json={"sheetUrl": "https://other"})
    assert client.report("ITEMS_REPORT", licenses="LIC-1", format="googleSheets") == SHEET
    assert params_of(router)["contentType"] == "googleSheets"
    assert len(router.calls) == 1  # the redirect is not followed


def test_google_sheets_falls_back_to_body_url(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, json={"sheetUrl": SHEET})
    assert client.report("ITEMS_REPORT", licenses="LIC-1", format="googleSheets") == SHEET


def test_google_sheets_without_url_returns_body(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, json={"status": "queued"})
    assert client.report("ITEMS_REPORT", licenses="LIC-1", format="googleSheets") == {"status": "queued"}


@pytest.mark.parametrize(
    ("content", "content_type", "expected"),
    [(b"", "application/json", None), (b"<html>sheet</html>", "text/html", b"<html>sheet</html>"), (b"[1]", "application/json", [1])],
)
def test_google_sheets_unexpected_body(
    client: T3Client, router: Router, content: bytes, content_type: str, expected: Any
) -> None:
    router.add("GET", REPORT, content=content, headers={"content-type": content_type})
    assert client.report("ITEMS_REPORT", licenses="LIC-1", format="googleSheets") == expected


def test_google_sheets_with_email_shares_the_sheet(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, status=302, headers={"Location": SHEET}, json={"sheetUrl": SHEET})
    client.report("ITEMS_REPORT", licenses="LIC-1", format="googleSheets", email="a@example.com")
    params = params_of(router)
    assert params["email"] == "a@example.com"
    assert "delivery" not in params


# --------------------------------------------------------------------------- email delivery


def test_email_delivery(client: T3Client, router: Router) -> None:
    router.add("GET", REPORT, json={"message": "Report will be emailed"})
    result = client.report("ITEMS_REPORT", licenses="LIC-1", delivery="email", email="a@example.com")
    assert result == {"message": "Report will be emailed"}
    params = params_of(router)
    assert params["delivery"] == "email"
    assert params["email"] == "a@example.com"
    assert router.calls[0].extensions["timeout"]["read"] == REPORT_TIMEOUT


def test_email_delivery_needs_email(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="needs email="):
        client.report("ITEMS_REPORT", licenses="LIC-1", delivery="email")
    assert router.calls == []


def test_email_without_delivery_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match='only applies with delivery="email"'):
        client.report("ITEMS_REPORT", licenses="LIC-1", email="a@example.com")
    with pytest.raises(ValueError, match='only applies with delivery="email"'):
        client.report("ITEMS_REPORT", licenses="LIC-1", email="a@example.com", delivery="inline")
    assert router.calls == []


def test_inline_delivery_is_sent(client: T3Client, csv_report: Router) -> None:
    assert client.report("ITEMS_REPORT", licenses="LIC-1", delivery="inline") == CSV
    assert params_of(csv_report)["delivery"] == "inline"


# --------------------------------------------------------------------------- report_url


def test_report_url(client: T3Client, router: Router, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        url = client.report_url(
            "ITEMS_REPORT",
            licenses=["LIC-1", "LIC-2"],
            format="xlsx",
            columns=["name", "id"],
            filter=["name__contains:flower"],
            filter_logic="and",
            sort="name:asc",
            row_limit=10,
            params={"prependCsvMetadata": "false"},
        )
    assert router.calls == []
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == "https://api.trackandtrace.tools"
    assert parts.path == REPORT
    query = parse_qs(parts.query)
    assert query == {
        "licenseNumber": ["LIC-1", "LIC-2"],
        "contentType": ["xlsx"],
        "columns": ["name,id"],
        "filter": ["name__contains:flower"],
        "filterLogic": ["and"],
        "sort": ["name:asc"],
        "rowLimit": ["10"],
        "prependCsvMetadata": ["false"],
        "secretKey": ["test-secret-key"],
    }
    assert URL_WARNING in caplog.text


def test_report_url_defaults(router: Router) -> None:
    with make_client(router, license="LIC-3", base_url="https://sandbox.example.test/") as c:
        url = c.report_url(REPORT)
    parts = urlsplit(url)
    assert parts.netloc == "sandbox.example.test"
    assert parse_qs(parts.query) == {
        "licenseNumber": ["LIC-3"],
        "contentType": ["csv"],
        "secretKey": ["test-secret-key"],
    }


def test_report_url_warns_every_call(client: T3Client, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        client.report_url("ITEMS_REPORT", licenses="LIC-1")
        client.report_url("ITEMS_REPORT", licenses="LIC-1")
    warnings = [r for r in caplog.records if URL_WARNING in r.getMessage()]
    assert len(warnings) == 2
    assert all(r.levelno == logging.WARNING for r in warnings)


def test_report_url_needs_a_secret_key(router: Router) -> None:
    with make_client(router, auth=BearerAuth("a.b.c")) as c, pytest.raises(T3Error, match="needs a secret key"):
        c.report_url("ITEMS_REPORT", licenses="LIC-1")
    assert router.calls == []


def test_report_url_checks_arguments(client: T3Client) -> None:
    with pytest.raises(ValueError, match="format must be one of"):
        client.report_url("ITEMS_REPORT", licenses="LIC-1", format="pdf")
    with pytest.raises(ValueError, match="licenses="):
        client.report_url("ITEMS_REPORT")
    with pytest.raises(SpecError):
        client.report_url("METRC_ACTIVE_ITEMS", licenses="LIC-1")
