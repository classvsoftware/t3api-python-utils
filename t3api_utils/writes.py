"""Write results and the bulk validate-then-submit helper.

How a write behaves depends on the route's kind in the spec:

* ``metrc_write`` routes take ``submit``. Without ``submit=True`` they are a
  dry run: the server validates and nothing reaches Metrc.
* ``immediate_write`` routes (auth, tag lists, label layouts, saved reports,
  support tickets) take effect at once and have no dry run.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx2

from t3api_utils import _console
from t3api_utils.errors import APIError, AuthError

if TYPE_CHECKING:
    from t3api_utils.client import T3Client

logger = logging.getLogger("t3api_utils")

OnError = Literal["stop", "skip"]
RowStatus = Literal["valid", "invalid", "submitted", "failed", "not_sent"]


@dataclass
class WriteResult:
    """What a write returned.

    Attributes:
        dry_run: True if the server only validated the request.
        message: The server's ``message``: ``"Dry run"`` or ``"Success"`` for Metrc writes.
        data: The parsed response body.
        response: The ``httpx2.Response``.
    """

    dry_run: bool
    message: str | None
    data: Any
    response: httpx2.Response = field(repr=False)


@dataclass
class RowResult:
    """One row of a bulk write."""

    index: int
    row: Mapping[str, Any]
    status: RowStatus = "not_sent"
    message: str | None = None
    data: Any = None
    error: APIError | None = field(default=None, repr=False)


@dataclass
class BulkResult:
    """Every row's outcome, in input order."""

    endpoint: str
    rows: list[RowResult]
    submitted: bool = False

    def __iter__(self) -> Iterator[RowResult]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def by_status(self, status: RowStatus) -> list[RowResult]:
        """The rows with one status."""
        return [r for r in self.rows if r.status == status]

    @property
    def invalid(self) -> list[RowResult]:
        """Rows that failed the dry run."""
        return self.by_status("invalid")

    @property
    def failed(self) -> list[RowResult]:
        """Rows whose submit the server rejected."""
        return self.by_status("failed")

    @property
    def ok(self) -> bool:
        """True when no row was invalid or failed."""
        return not self.invalid and not self.failed

    def counts(self) -> dict[str, int]:
        """How many rows have each status."""
        counts: dict[str, int] = {}
        for r in self.rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    def summary(self) -> str:
        """One line, e.g. ``POST /v2/items/discontinue: 3 submitted, 1 invalid``."""
        parts = [f"{n} {status.replace('_', ' ')}" for status, n in sorted(self.counts().items())]
        return f"{self.endpoint}: " + (", ".join(parts) if parts else "no rows")

    def to_csv(self, path: str | Path) -> Path:
        """Write one line per row: index, status, message, and the row as JSON."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["index", "status", "message", "row"])
            for r in self.rows:
                writer.writerow(
                    [r.index, r.status, r.message or "", json.dumps(r.row, default=str, ensure_ascii=False)]
                )
        return target


def _message(data: Any) -> str | None:
    if isinstance(data, dict) and isinstance(data.get("message"), str):
        return str(data["message"])
    return None


def _show_invalid(result: BulkResult, limit: int = 20) -> None:
    table = _console.table(f"{len(result.invalid)} row(s) failed validation")
    table.add_column("#", style="magenta", justify="right")
    table.add_column("Row", style="bright_white")
    table.add_column("Error", style="cyan")
    for r in result.invalid[:limit]:
        table.add_row(str(r.index), json.dumps(r.row, default=str)[:60], r.message or "")
    _console.console.print(table)
    if len(result.invalid) > limit:
        _console.info(f"…and {len(result.invalid) - limit} more.")


def bulk(
    client: T3Client,
    endpoint: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    license: str | None = None,
    method: str | None = None,
    submit: bool = False,
    confirm: bool = False,
    on_error: OnError = "stop",
    log_to: str | Path | None = None,
    progress: bool | None = None,
    path_params: Mapping[str, Any] | None = None,
) -> BulkResult:
    """Send many writes safely, one row per request.

    For Metrc write routes:

    1. Every row is sent as a dry run and its result recorded.
    2. If any row failed, stop and return the results. In a terminal, show the
       failures and ask whether to submit only the valid rows.
       ``on_error="skip"`` does that without asking.
    3. With ``submit=True``, send each valid row with ``submit=true``, in order.
       With ``on_error="stop"``, the first failed submit stops the rest.

    Routes with no dry run (``immediate_write``) skip validation, so they need
    ``confirm=True``.

    ``log_to`` writes the results to a CSV file.
    """
    if on_error not in ("stop", "skip"):
        raise ValueError('on_error must be "stop" or "skip".')
    path_params = dict(path_params or {})
    items = [RowResult(index=i, row=row) for i, row in enumerate(rows)]
    ep = client.spec.endpoint(
        endpoint,
        method=method,
        kind=("metrc_write", "immediate_write"),
        path_params=path_params.keys(),
    )
    result = BulkResult(endpoint=ep.label(), rows=items)
    show = _console.stderr_is_terminal() if progress is None else progress

    def send(item: RowResult, submit_flag: bool | None) -> None:
        write = client._write(
            ep.method,
            ep.path if not endpoint.startswith("/") else endpoint,
            license=license,
            params=None,
            json=dict(item.row),
            files=None,
            data=None,
            submit=submit_flag,
            timeout=None,
            path_params=path_params,
        )
        item.data = write.data
        item.message = write.message

    if ep.kind == "immediate_write":
        if not confirm:
            raise ValueError(
                f"{ep.label()} takes effect immediately and has no dry run, so bulk() can't "
                "validate rows first. Pass confirm=True to send them anyway."
            )
        _submit(result, items, send, None, on_error, show)
        return _finish(result, log_to)

    with _console.progress_bar("Validating", len(items), show and bool(items)) as advance:
        for item in items:
            try:
                send(item, None)
                item.status = "valid"
            except AuthError:
                raise
            except APIError as exc:
                item.status = "invalid"
                item.message = exc.detail or str(exc)
                item.error = exc
            advance(1)

    valid = [i for i in items if i.status == "valid"]
    if result.invalid:
        logger.warning("%d of %d rows failed validation.", len(result.invalid), len(items))
        if not submit:
            return _finish(result, log_to)
        if on_error == "stop":
            if not valid or not _console.is_interactive():
                return _finish(result, log_to)
            _show_invalid(result)
            if not _console.confirm(f"Submit only the {len(valid)} valid row(s)?", default=False):
                return _finish(result, log_to)

    if submit:
        _submit(result, valid, send, True, on_error, show)
    return _finish(result, log_to)


def _submit(
    result: BulkResult,
    items: list[RowResult],
    send: Any,
    submit_flag: bool | None,
    on_error: OnError,
    show: bool,
) -> None:
    result.submitted = True
    stopped = False
    with _console.progress_bar("Submitting", len(items), show and bool(items)) as advance:
        for item in items:
            if stopped:
                item.status = "not_sent"
                continue
            try:
                send(item, submit_flag)
                item.status = "submitted"
            except AuthError:
                raise
            except APIError as exc:
                item.status = "failed"
                item.message = exc.detail or str(exc)
                item.error = exc
                if on_error == "stop":
                    stopped = True
                    logger.warning("Row %d failed; not sending the rest.", item.index)
            advance(1)


def _finish(result: BulkResult, log_to: str | Path | None) -> BulkResult:
    if log_to is not None:
        result.to_csv(log_to)
    logger.info("%s", result.summary())
    return result
