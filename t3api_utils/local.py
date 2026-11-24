"""Local helpers: filter rows against a CSV, export to CSV or JSON, read files back."""

from __future__ import annotations

import csv
import json
import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("t3api_utils")

PRIORITY_FIELDS = (
    "hostname",
    "licenseNumber",
    "retrievedAt",
    "dataModel",
    "index",
    "id",
    "label",
    "name",
)
OnUnmatched = Literal["warn", "error", "skip"]
_SEPARATORS = (os.sep, os.altsep or os.sep)


def get_path(row: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path such as ``item.name``. Returns ``None`` if any part is missing."""
    if path in row:
        return row[path]
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _has_path(row: Mapping[str, Any], path: str) -> bool:
    if path in row:
        return True
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return False
        value = value[part]
    return True


def _key_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value).strip()


def _read_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        records = [dict(r) for r in reader]
        return list(reader.fieldnames or []), records


def filter_rows(
    rows: Sequence[Mapping[str, Any]],
    match: str | Path | Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    on_unmatched: OnUnmatched = "warn",
) -> list[dict[str, Any]]:
    """Keep the rows that match a CSV/TSV file or a list of dicts.

    Args:
        rows: The rows to filter, e.g. from :meth:`T3Client.collect`.
        match: A CSV or TSV path, or a list of dicts.
        columns: Columns to compare. Defaults to every column of the match
            file. Dotted paths such as ``item.name`` reach into nested rows.
        on_unmatched: What to do when a match line finds no row: ``"warn"``,
            ``"error"`` (raise ValueError) or ``"skip"``.

    Values compare as stripped strings. Results follow the order of ``match``.
    """
    if on_unmatched not in ("warn", "error", "skip"):
        raise ValueError('on_unmatched must be "warn", "error" or "skip".')
    if isinstance(match, (str, Path)):
        header, records = _read_table(Path(match))
    else:
        records = [dict(m) for m in match]
        header = list(records[0]) if records else []
    keys = list(columns or header)
    if not keys:
        raise ValueError("No columns to match on.")
    if not records:
        return []

    missing = [c for c in keys if not any(_has_path(r, c) for r in rows)]
    if missing and rows:
        available = sorted({k for r in rows for k in r})
        raise ValueError(
            f"Column(s) {', '.join(missing)} aren't in the rows. Available: {', '.join(available[:30])}"
        )

    index: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        index.setdefault(tuple(_key_value(get_path(row, c)) for c in keys), []).append(row)

    matched: list[dict[str, Any]] = []
    taken: set[int] = set()
    unmatched: list[tuple[str, ...]] = []
    for record in records:
        key = tuple(_key_value(get_path(record, c)) for c in keys)
        found = index.get(key)
        if not found:
            unmatched.append(key)
            continue
        for row in found:
            if id(row) not in taken:
                taken.add(id(row))
                matched.append(dict(row))

    if unmatched and on_unmatched != "skip":
        shown = "; ".join(", ".join(k) for k in unmatched[:10])
        more = f" (and {len(unmatched) - 10} more)" if len(unmatched) > 10 else ""
        message = f"{len(unmatched)} of {len(records)} match line(s) found no row: {shown}{more}"
        if on_unmatched == "error":
            raise ValueError(message)
        logger.warning("%s", message)
    return matched


# --------------------------------------------------------------------------- export


def flatten(row: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Nested objects become dotted keys; lists become JSON text."""
    flat: dict[str, Any] = {}
    for key, value in row.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            if value:
                flat.update(flatten(value, f"{name}."))
            else:
                flat[name] = ""
        elif isinstance(value, (list, tuple)):
            flat[name] = json.dumps(value, ensure_ascii=False, default=str)
        elif value is None:
            flat[name] = ""
        else:
            flat[name] = value
    return flat


def ordered_columns(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """1.x's priority fields first, then every other column alphabetically."""
    seen: set[str] = set()
    for row in rows:
        seen.update(row)
    first = [c for c in PRIORITY_FIELDS if c in seen]
    return first + sorted(seen - set(first))


def default_path(rows: Sequence[Mapping[str, Any]], extension: str) -> Path:
    """``<dataModel>__<license>__<timestamp>.<ext>`` in the current folder."""
    sample = rows[0] if rows else {}
    parts = [str(sample.get("dataModel") or "rows")]
    if sample.get("licenseNumber"):
        parts.append(str(sample["licenseNumber"]))
    parts.append(datetime.now().strftime("%Y-%m-%dT%H-%M-%S"))
    safe = ["".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in p) for p in parts]
    return Path("__".join(safe) + f".{extension}")


def _target(path: str | Path | None, rows: Sequence[Mapping[str, Any]], extension: str) -> Path:
    """``path``; or the default file name, in ``path`` when it's a folder."""
    if path is None:
        return default_path(rows, extension)
    text = os.fspath(path)
    if text.endswith(_SEPARATORS) or Path(text).is_dir():
        return Path(text) / default_path(rows, extension)
    return Path(text)


def to_csv(
    rows: Sequence[Mapping[str, Any]],
    path: str | Path | None = None,
    *,
    columns: Sequence[str] | None = None,
    strip_empty: bool = False,
) -> Path:
    """Write rows to CSV (UTF-8 with a BOM, so Excel opens it cleanly). Returns the path.

    Nested objects become dotted columns (``item.name``); lists are written as
    JSON text. ``columns`` picks and orders columns; ``strip_empty`` drops
    columns that are empty in every row.

    Without ``path``, the file is ``<dataModel>__<license>__<timestamp>.csv``
    in the current folder. A ``path`` that is an existing folder, or ends with
    ``/``, gets that default name inside it (``to_csv(rows, "output/")``).
    Missing folders are created.
    """
    flat = [flatten(r) for r in rows]
    fields = list(columns) if columns else ordered_columns(flat)
    if strip_empty:
        fields = [f for f in fields if any(r.get(f) not in (None, "") for r in flat)]
    target = _target(path, rows, "csv")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat)
    return target


def to_json(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    path: str | Path | None = None,
    *,
    lines: bool = False,
) -> Path:
    """Write rows as indented JSON, or one object per line with ``lines=True``.

    ``path`` works as in :func:`to_csv`: leave it out, or pass a folder, for a
    ``<dataModel>__<license>__<timestamp>.json`` (or ``.jsonl``) file name.
    """
    data = list(rows) if not isinstance(rows, Mapping) else rows
    sample = data if isinstance(data, list) else [data]
    target = _target(path, sample, "jsonl" if lines else "json")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        if lines:
            for row in sample:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        else:
            json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
            handle.write("\n")
    return target


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read rows back from a JSON, JSON Lines, CSV or TSV file."""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in (".csv", ".tsv", ".tab"):
        return [dict(r) for r in _read_table(source)[1]]
    text = source.read_text(encoding="utf-8-sig")
    if suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        inner = data.get("data")
        return list(inner) if isinstance(inner, list) else [data]
    if isinstance(data, list):
        return [r if isinstance(r, dict) else {"value": r} for r in data]
    return [{"value": data}]
