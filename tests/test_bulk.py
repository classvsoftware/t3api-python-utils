"""client.bulk(): validate, then submit; failures, prompts, immediate routes, BulkResult."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import pytest

from t3api_utils import _console
from t3api_utils.client import T3Client
from t3api_utils.errors import AuthError, SpecError, ValidationError
from t3api_utils.writes import BulkResult, RowResult
from tests.conftest import Router

DISCONTINUE = "/v2/items/discontinue"


@dataclass
class FakeDiscontinue:
    """POST /v2/items/discontinue: rejects some ids on validation or on submit."""

    invalid: set[int] = field(default_factory=set)
    fail_on_submit: set[int] = field(default_factory=set)
    unauthorized: set[int] = field(default_factory=set)
    empty_error_body: bool = False
    dry_runs: list[int] = field(default_factory=list)
    submits: list[int] = field(default_factory=list)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        item_id = int(json.loads(request.content)["id"])
        submit = request.url.params.get("submit") == "true"
        (self.submits if submit else self.dry_runs).append(item_id)
        if item_id in self.unauthorized:
            return httpx2.Response(401, json={"detail": "key revoked"})
        if item_id in self.invalid or (submit and item_id in self.fail_on_submit):
            if self.empty_error_body:
                return httpx2.Response(400)
            return httpx2.Response(400, json={"detail": f"Item {item_id} can't be discontinued"})
        return httpx2.Response(200, json={"message": "Success" if submit else "Dry run", "id": item_id})


def rows(*ids: int) -> list[dict[str, Any]]:
    return [{"id": i} for i in ids]


def statuses(result: BulkResult) -> list[str]:
    return [r.status for r in result]


@pytest.fixture
def api(router: Router) -> FakeDiscontinue:
    fake = FakeDiscontinue()
    router.add("POST", DISCONTINUE, handler=fake)
    return fake


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A terminal whose user answers yes; returns the questions asked."""
    asked: list[str] = []

    def confirm(text: str, *, default: bool = True) -> bool:
        asked.append(text)
        return True

    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    monkeypatch.setattr(_console, "confirm", confirm)
    return asked


def no_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    def confirm(text: str, *, default: bool = True) -> bool:
        raise AssertionError(f"unexpected prompt: {text}")

    monkeypatch.setattr(_console, "confirm", confirm)


# --------------------------------------------------------------------------- validation only


def test_validate_only_sends_dry_runs(client: T3Client, api: FakeDiscontinue) -> None:
    result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1")
    assert statuses(result) == ["valid", "valid", "valid"]
    assert result.submitted is False
    assert result.ok
    assert api.dry_runs == [1, 2, 3]
    assert api.submits == []
    assert [r.message for r in result] == ["Dry run"] * 3
    assert result.rows[0].data == {"message": "Dry run", "id": 1}
    assert result.endpoint == "POST /v2/items/discontinue"


def test_bulk_sends_license_and_rows(client: T3Client, router: Router, api: FakeDiscontinue) -> None:
    client.bulk(DISCONTINUE, rows(1), license="LIC-1")
    request = router.calls[0]
    assert request.url.params["licenseNumber"] == "LIC-1"
    assert json.loads(request.content) == {"id": 1}


def test_invalid_rows_without_submit_return_results(
    client: T3Client, api: FakeDiscontinue, caplog: pytest.LogCaptureFixture
) -> None:
    api.invalid = {2}
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1")
    assert statuses(result) == ["valid", "invalid", "valid"]
    assert not result.ok
    bad = result.invalid[0]
    assert bad.index == 1
    assert bad.message == "Item 2 can't be discontinued"
    assert isinstance(bad.error, ValidationError)
    assert api.submits == []
    assert "1 of 3 rows failed validation" in caplog.text
    assert "POST /v2/items/discontinue: 1 invalid, 2 valid" in caplog.text


def test_invalid_row_message_falls_back_to_error_text(client: T3Client, api: FakeDiscontinue) -> None:
    api.invalid = {1}
    api.empty_error_body = True
    result = client.bulk(DISCONTINUE, rows(1), license="LIC-1")
    message = result.rows[0].message
    assert message is not None and message.startswith("400 Bad Request from POST /v2/items/discontinue")


# --------------------------------------------------------------------------- submit


def test_all_valid_then_submit(client: T3Client, api: FakeDiscontinue, monkeypatch: pytest.MonkeyPatch) -> None:
    no_prompt(monkeypatch)
    result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1", submit=True)
    assert statuses(result) == ["submitted"] * 3
    assert result.submitted is True
    assert result.ok
    assert api.dry_runs == [1, 2, 3]
    assert api.submits == [1, 2, 3]
    assert [r.message for r in result] == ["Success"] * 3


def test_invalid_with_stop_non_interactive_submits_nothing(
    client: T3Client, api: FakeDiscontinue, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_prompt(monkeypatch)
    api.invalid = {2}
    result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1", submit=True)
    assert statuses(result) == ["valid", "invalid", "valid"]
    assert result.submitted is False
    assert api.submits == []


def test_invalid_with_stop_interactive_confirmed_submits_valid_rows(
    client: T3Client,
    api: FakeDiscontinue,
    interactive: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    api.invalid = {2}
    result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1", submit=True)
    assert interactive == ["Submit only the 2 valid row(s)?"]
    assert "1 row(s) failed validation" in capsys.readouterr().err
    assert statuses(result) == ["submitted", "invalid", "submitted"]
    assert result.submitted is True
    assert api.submits == [1, 3]


def test_invalid_with_stop_interactive_declined_submits_nothing(
    client: T3Client, api: FakeDiscontinue, interactive: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def decline(text: str, *, default: bool = True) -> bool:
        interactive.append(text)
        assert default is False
        return False

    monkeypatch.setattr(_console, "confirm", decline)
    api.invalid = {1}
    result = client.bulk(DISCONTINUE, rows(1, 2), license="LIC-1", submit=True)
    assert len(interactive) == 1
    assert statuses(result) == ["invalid", "valid"]
    assert result.submitted is False
    assert api.submits == []


def test_all_invalid_interactive_does_not_ask(
    client: T3Client, api: FakeDiscontinue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    no_prompt(monkeypatch)
    api.invalid = {1, 2}
    result = client.bulk(DISCONTINUE, rows(1, 2), license="LIC-1", submit=True)
    assert statuses(result) == ["invalid", "invalid"]
    assert api.submits == []


def test_many_failures_table_is_truncated(
    client: T3Client, api: FakeDiscontinue, interactive: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    api.invalid = set(range(1, 26))
    client.bulk(DISCONTINUE, rows(*range(1, 28)), license="LIC-1", submit=True)
    err = capsys.readouterr().err
    assert "25 row(s) failed validation" in err
    assert "and 5 more" in err
    assert api.submits == [26, 27]


def test_on_error_skip_submits_valid_rows_without_asking(
    client: T3Client, api: FakeDiscontinue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    no_prompt(monkeypatch)
    api.invalid = {2}
    result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1", submit=True, on_error="skip")
    assert statuses(result) == ["submitted", "invalid", "submitted"]
    assert api.submits == [1, 3]


def test_submit_failure_with_stop_marks_the_rest_not_sent(
    client: T3Client, api: FakeDiscontinue, caplog: pytest.LogCaptureFixture
) -> None:
    api.fail_on_submit = {2}
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        result = client.bulk(DISCONTINUE, rows(1, 2, 3, 4), license="LIC-1", submit=True)
    assert statuses(result) == ["submitted", "failed", "not_sent", "not_sent"]
    assert api.submits == [1, 2]
    failed = result.failed[0]
    assert failed.message == "Item 2 can't be discontinued"
    assert isinstance(failed.error, ValidationError)
    assert not result.ok
    assert "Row 1 failed; not sending the rest." in caplog.text


def test_submit_failure_with_skip_continues(client: T3Client, api: FakeDiscontinue) -> None:
    api.fail_on_submit = {2}
    result = client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1", submit=True, on_error="skip")
    assert statuses(result) == ["submitted", "failed", "submitted"]
    assert api.submits == [1, 2, 3]


def test_auth_error_during_validation_propagates(client: T3Client, api: FakeDiscontinue) -> None:
    api.unauthorized = {2}
    with pytest.raises(AuthError):
        client.bulk(DISCONTINUE, rows(1, 2, 3), license="LIC-1", submit=True)
    assert api.dry_runs == [1, 2]
    assert api.submits == []


def test_auth_error_during_submit_propagates(client: T3Client, router: Router) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.params.get("submit") == "true":
            return httpx2.Response(401, json={"detail": "revoked"})
        return httpx2.Response(200, json={"message": "Dry run"})

    router.add("POST", DISCONTINUE, handler=handler)
    with pytest.raises(AuthError):
        client.bulk(DISCONTINUE, rows(1, 2), license="LIC-1", submit=True)
    assert len(router.requests("POST", DISCONTINUE)) == 3  # 2 dry runs, 1 submit


def test_progress_bars_do_not_crash(client: T3Client, api: FakeDiscontinue) -> None:
    result = client.bulk(DISCONTINUE, rows(1, 2), license="LIC-1", submit=True, progress=True)
    assert statuses(result) == ["submitted", "submitted"]


def test_empty_rows(client: T3Client, api: FakeDiscontinue) -> None:
    result = client.bulk(DISCONTINUE, [], license="LIC-1", submit=True, progress=True)
    assert len(result) == 0
    assert result.ok
    assert result.summary() == "POST /v2/items/discontinue: no rows"


# --------------------------------------------------------------------------- arguments


def test_invalid_on_error_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="on_error"):
        client.bulk(DISCONTINUE, rows(1), license="LIC-1", on_error="ignore")  # type: ignore[arg-type]
    assert router.calls == []


def test_non_write_endpoint_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError):
        client.bulk("METRC_ACTIVE_ITEMS", rows(1), license="LIC-1")
    assert router.calls == []


def test_missing_license_raises_before_sending(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="license="):
        client.bulk(DISCONTINUE, rows(1))
    assert router.calls == []


# --------------------------------------------------------------------------- immediate routes


def test_immediate_route_needs_confirm(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="confirm=True"):
        client.bulk("/v2/tag-lists/{tag_list_id}/scan", rows(1), tag_list_id="tl-1")
    assert router.calls == []


def test_immediate_route_with_confirm_sends_each_row_once(client: T3Client, router: Router) -> None:
    router.add("POST", "/v2/tag-lists/{tag_list_id}/scan", json={"scanned": 1})
    payload = [{"handles": ["A"]}, {"handles": ["B"]}]
    result = client.bulk(
        "/v2/tag-lists/{tag_list_id}/scan", payload, tag_list_id="tl 1", confirm=True, method="POST"
    )
    assert statuses(result) == ["submitted", "submitted"]
    assert result.submitted is True
    assert [json.loads(r.content) for r in router.calls] == payload
    assert all(r.url.raw_path == b"/v2/tag-lists/tl%201/scan" for r in router.calls)
    assert all("submit" not in r.url.params for r in router.calls)
    assert result.rows[0].data == {"scanned": 1}


def test_immediate_route_failure_with_stop(client: T3Client, router: Router) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if json.loads(request.content)["name"] == "bad":
            return httpx2.Response(422, json={"detail": "name taken"})
        return httpx2.Response(200, json={"id": "x"})

    router.add("POST", "/v2/tag-lists", handler=handler)
    result = client.bulk(
        "/v2/tag-lists", [{"name": "ok"}, {"name": "bad"}, {"name": "later"}], confirm=True
    )
    assert statuses(result) == ["submitted", "failed", "not_sent"]
    assert result.rows[1].message == "name taken"


# --------------------------------------------------------------------------- log_to and BulkResult


def test_log_to_writes_csv(client: T3Client, api: FakeDiscontinue, tmp_path: Path) -> None:
    api.invalid = {2}
    target = tmp_path / "logs" / "results.csv"
    result = client.bulk(DISCONTINUE, [{"id": 1}, {"id": 2, "note": "café"}], license="LIC-1", log_to=target)
    assert target.is_file()
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel
    with target.open(newline="", encoding="utf-8-sig") as handle:
        lines = list(csv.reader(handle))
    assert lines == [
        ["index", "status", "message", "row"],
        ["0", "valid", "Dry run", '{"id": 1}'],
        ["1", "invalid", "Item 2 can't be discontinued", '{"id": 2, "note": "café"}'],
    ]
    assert len(result) == 2


def test_log_to_accepts_a_string_path(client: T3Client, api: FakeDiscontinue) -> None:
    client.bulk(DISCONTINUE, rows(1), license="LIC-1", log_to="results.csv")
    assert Path("results.csv").is_file()


def test_bulk_result_helpers() -> None:
    result = BulkResult(
        endpoint="POST /v2/x",
        rows=[
            RowResult(index=0, row={"id": 1}, status="submitted"),
            RowResult(index=1, row={"id": 2}, status="failed", message="boom"),
            RowResult(index=2, row={"id": 3}),
            RowResult(index=3, row={"id": 4}, status="submitted"),
        ],
        submitted=True,
    )
    assert len(result) == 4
    assert [r.index for r in result] == [0, 1, 2, 3]
    assert result.counts() == {"submitted": 2, "failed": 1, "not_sent": 1}
    assert result.summary() == "POST /v2/x: 1 failed, 1 not sent, 2 submitted"
    assert [r.index for r in result.by_status("submitted")] == [0, 3]
    assert [r.index for r in result.failed] == [1]
    assert result.invalid == []
    assert result.ok is False
    assert result.rows[2].status == "not_sent"
    assert "error" not in repr(result.rows[1])


def test_bulk_result_ok_when_clean() -> None:
    result = BulkResult(endpoint="POST /v2/x", rows=[RowResult(index=0, row={}, status="valid")])
    assert result.ok is True
    assert result.counts() == {"valid": 1}
