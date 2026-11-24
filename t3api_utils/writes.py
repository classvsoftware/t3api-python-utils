"""Write results and the bulk validate-then-submit helper.

How a write behaves depends on the route's kind in the spec:

* ``metrc_write`` routes take ``submit``. Without ``submit=True`` they are a
  dry run: T3 checks the request statically (format, required fields and
  types, not whether the records it names exist) and nothing reaches Metrc.
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
from typing import TYPE_CHECKING, Any, Literal, get_args

import httpx2
from rich.markup import escape

from t3api_utils import _console
from t3api_utils.errors import APIError, AuthError, NotInteractive

if TYPE_CHECKING:
    from t3api_utils.client import T3Client
    from t3api_utils.spec.registry import Endpoint

logger = logging.getLogger("t3api_utils")

OnError = Literal["stop", "skip"]
RowStatus = Literal["valid", "invalid", "submitted", "failed", "not_sent"]
_STATUS_LABELS = {"valid": "passed validation", "invalid": "failed validation", "not_sent": "not sent"}
STATIC_VALIDATION = (
    "A dry run checks format, required fields and types, not whether the records it names exist."
)


@dataclass
class WriteResult:
    """What a write returned.

    Attributes:
        dry_run: True if T3 only checked the request: format, required fields
            and types, not whether the records it names exist. Nothing reached
            Metrc.
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
    """One row of a bulk write.

    ``status`` is ``valid`` (passed the dry run's static checks, not
    submitted), ``invalid``, ``submitted``, ``failed`` or ``not_sent``.
    """

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
        """Rows that failed validation (the dry run)."""
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
        """One line, e.g. ``POST /v2/items/discontinue: 1 failed validation, 3 submitted``."""
        return f"{self.endpoint}: {self._counts_text()}"

    def _counts_text(self) -> str:
        counts = self.counts()
        parts = [
            f"{counts[status]} {_STATUS_LABELS.get(status, status)}"
            for status in get_args(RowStatus)
            if status in counts
        ]
        return ", ".join(parts) if parts else "no rows"

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


def _batches(items: list[RowResult], size: int) -> list[list[RowResult]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _rows_label(batch: list[RowResult]) -> str:
    if len(batch) == 1:
        return f"Row {batch[0].index}"
    return f"Rows {batch[0].index}-{batch[-1].index}"


def _ask_to_submit(
    client: T3Client,
    ep: Endpoint,
    license: str | None,
    result: BulkResult,
    rows: list[RowResult],
) -> bool:
    """Show what's about to be sent and ask, default no."""
    lic = client._license_for(ep, license)
    lic_text = ", ".join(lic) if isinstance(lic, list) else lic
    _console.console.print(f"[bold bright_magenta]── {escape(ep.label())} ──[/bold bright_magenta]")
    if lic_text:
        _console.console.print(f"[magenta]License:[/magenta] {escape(lic_text)}")
    if client.sandbox:
        _console.console.print(f"[magenta]Sandbox:[/magenta] yes ({escape(client.hostname or 'unknown host')})")
    where = "the Metrc sandbox" if client.sandbox else "Metrc"
    suffix = f" for {lic_text}" if lic_text else ""
    if ep.kind == "immediate_write":
        _console.warning("This route takes effect immediately. It has no dry run, so nothing was checked.")
        return _console.confirm(f"Send {len(rows)} row(s) to {ep.method} {ep.path}{suffix}?", default=False)
    _console.console.print(f"[magenta]Rows:[/magenta] {escape(result._counts_text())}")
    _console.info(STATIC_VALIDATION)
    if result.invalid:
        _show_invalid(result)
        question = f"Submit the {len(rows)} valid row(s) to {where}{suffix}?"
    else:
        question = f"Submit {len(rows)} row(s) to {where}{suffix}?"
    return _console.confirm(question, default=False)


def bulk(
    client: T3Client,
    endpoint: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    license: str | None = None,
    method: str | None = None,
    submit: bool | Literal["ask"] = False,
    confirm: bool = False,
    on_error: OnError = "stop",
    log_to: str | Path | None = None,
    progress: bool | None = None,
    path_params: Mapping[str, Any] | None = None,
    dynamic: bool = False,
    batch_size: int = 1,
) -> BulkResult:
    """Send many writes safely: validate every row, then submit.

    For Metrc write routes:

    1. Every row is sent as a dry run and its result recorded. A dry run
       checks format, required fields and types, not whether the records a
       row names exist, so ``valid`` means "passed validation", not "Metrc
       will accept it".
    2. ``submit=False`` stops here. ``submit="ask"`` shows a summary (and any
       failures) and asks whether to submit, default no. ``submit=True``
       carries on without asking unless some rows failed; then, in a
       terminal, it shows the failures and asks whether to submit only the
       valid rows. ``on_error="skip"`` submits them without asking.
    3. Each valid row is sent with ``submit=true``, in order. With
       ``on_error="stop"``, the first failed submit stops the rest.

    Each row is one object. On routes whose body is a list (most Metrc
    writes), rows are wrapped in a list for you.

    Routes with no dry run (``immediate_write``) can't be validated first, so
    they need ``confirm=True`` ("I know this takes effect at once"), or
    ``submit="ask"`` to ask a person before sending.

    Args:
        client: The client to send with.
        endpoint: The write route's path (or endpoint ID).
        rows: One mapping per object to write.
        license: Fills ``licenseNumber``. Defaults to the client's license
            when the route requires one.
        method: Picks the operation when a path has several write methods.
        submit: ``False`` validates only, ``True`` submits the valid rows,
            ``"ask"`` asks first. ``"ask"`` raises
            :class:`~t3api_utils.errors.NotInteractive` without a terminal,
            before sending anything, so a scheduled job can't hang or quietly
            submit nothing.
        confirm: Required for routes with no dry run, unless ``submit="ask"``.
        on_error: ``"stop"`` (the default) or ``"skip"``, as described above.
        log_to: Write the results to this CSV file.
        progress: Show progress bars. Defaults to on when stderr is a terminal.
        path_params: Values for the route's path parameters.
        dynamic: Also ask T3 for the route's dynamic checks
            (``applyDynamicValidation``). What they cover depends on the route.
        batch_size: Rows per request, on routes whose body is a list. A
            request that fails marks every row in it with the same error, so
            the default of 1 keeps each row's error separate.

    Raises:
        ValueError: a bad ``submit``, ``on_error`` or ``batch_size``; an
            immediate route without ``confirm=True``; ``batch_size`` above 1 on
            a route that takes one object; ``dynamic=True`` on a route without
            dynamic validation.
        NotInteractive: ``submit="ask"`` without a terminal.
        AuthError: the credential was rejected. It stops the run whatever
            ``on_error`` says.
    """
    if on_error not in ("stop", "skip"):
        raise ValueError('on_error must be "stop" or "skip".')
    if not isinstance(submit, bool) and submit != "ask":
        raise ValueError('submit must be True, False or "ask".')
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    if submit == "ask" and not _console.is_interactive():
        raise NotInteractive(
            'submit="ask" needs a terminal to ask in. Pass submit=True to submit without asking.'
        )
    path_params = dict(path_params or {})
    items = [RowResult(index=i, row=row) for i, row in enumerate(rows)]
    ep = client.spec.endpoint(
        endpoint,
        method=method,
        kind=("metrc_write", "immediate_write"),
        path_params=path_params.keys(),
    )
    if batch_size > 1 and not ep.body_is_array:
        raise ValueError(f"{ep.label()} takes one object per request, so batch_size must be 1.")
    result = BulkResult(endpoint=ep.label(), rows=items)
    show = _console.stderr_is_terminal() if progress is None else progress
    target = endpoint if endpoint.startswith("/") else ep.path

    def send(batch: list[RowResult], submit_flag: bool | None) -> None:
        body: Any = [dict(i.row) for i in batch] if ep.body_is_array else dict(batch[0].row)
        write = client._write(
            ep.method,
            target,
            license=license,
            params=None,
            json=body,
            files=None,
            data=None,
            submit=submit_flag,
            timeout=None,
            path_params=path_params,
            dynamic=dynamic,
        )
        for item in batch:
            item.data = write.data
            item.message = write.message

    if ep.kind == "immediate_write":
        if submit == "ask":
            if not items or not _ask_to_submit(client, ep, license, result, items):
                return _finish(result, log_to)
        elif not confirm:
            raise ValueError(
                f"{ep.label()} takes effect immediately and has no dry run, so bulk() can't "
                'validate rows first. Pass confirm=True to send them anyway, or submit="ask" '
                "to ask first."
            )
        _submit(result, items, send, None, on_error, show, batch_size)
        return _finish(result, log_to)

    with _console.progress_bar("Validating", len(items), show and bool(items)) as advance:
        for batch in _batches(items, batch_size):
            try:
                send(batch, None)
            except AuthError:
                raise
            except APIError as exc:
                for item in batch:
                    item.status = "invalid"
                    item.message = exc.detail or str(exc)
                    item.error = exc
            else:
                for item in batch:
                    item.status = "valid"
            advance(len(batch))

    valid = [i for i in items if i.status == "valid"]
    if result.invalid:
        logger.warning("%d of %d rows failed validation.", len(result.invalid), len(items))
    if not submit:
        return _finish(result, log_to)
    if submit == "ask":
        if not valid:
            if result.invalid:
                _show_invalid(result)
            return _finish(result, log_to)
        if not _ask_to_submit(client, ep, license, result, valid):
            return _finish(result, log_to)
    elif result.invalid and on_error == "stop":
        if not valid or not _console.is_interactive():
            return _finish(result, log_to)
        _show_invalid(result)
        if not _console.confirm(f"Submit only the {len(valid)} valid row(s)?", default=False):
            return _finish(result, log_to)

    _submit(result, valid, send, True, on_error, show, batch_size)
    return _finish(result, log_to)


def _submit(
    result: BulkResult,
    items: list[RowResult],
    send: Any,
    submit_flag: bool | None,
    on_error: OnError,
    show: bool,
    batch_size: int,
) -> None:
    result.submitted = True
    stopped = False
    with _console.progress_bar("Submitting", len(items), show and bool(items)) as advance:
        for batch in _batches(items, batch_size):
            if stopped:
                for item in batch:
                    item.status = "not_sent"
                continue
            try:
                send(batch, submit_flag)
            except AuthError:
                raise
            except APIError as exc:
                for item in batch:
                    item.status = "failed"
                    item.message = exc.detail or str(exc)
                    item.error = exc
                if on_error == "stop":
                    stopped = True
                    logger.warning("%s failed; not sending the rest.", _rows_label(batch))
            else:
                for item in batch:
                    item.status = "submitted"
            advance(len(batch))


def _finish(result: BulkResult, log_to: str | Path | None) -> BulkResult:
    if log_to is not None:
        result.to_csv(log_to)
    logger.info("%s", result.summary())
    return result
