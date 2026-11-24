"""Tag lists: server-side lists of handles (usually tag labels) that resolve to objects.

``client.tag_lists`` wraps ``/v2/tag-lists``. Resolving is all or nothing: if
any handle matches zero objects or several, the server answers 422 and
:class:`~t3api_utils.errors.TagListResolveError` carries the per-handle errors.
"""

from __future__ import annotations

import builtins
import csv
import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

from t3api_utils.local import get_path

if TYPE_CHECKING:
    from t3api_utils.client import T3Client

logger = logging.getLogger("t3api_utils")

BASE = "/v2/tag-lists"
MAX_ENTRIES = 5000
Visibility = Literal["USER", "LICENSE"]
Entry = str | Mapping[str, Any]


def _url(list_id: str, suffix: str = "") -> str:
    return f"{BASE}/{quote(str(list_id), safe='')}{suffix}"


def _chunks(items: Sequence[Any], size: int = MAX_ENTRIES) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def normalize_entries(entries: Iterable[Entry]) -> list[dict[str, Any]]:
    """Turn handles or entry dicts into entry dicts, dropping blanks and repeats.

    Handles match ignoring case and surrounding whitespace, so repeats are
    found the same way. The first copy of a handle wins.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    repeats = 0
    for entry in entries:
        item = {"handle": entry} if isinstance(entry, str) else dict(entry)
        handle = str(item.get("handle") or "").strip()
        if not handle:
            continue
        key = handle.lower()
        if key in seen:
            repeats += 1
            continue
        seen.add(key)
        item["handle"] = handle
        out.append(item)
    if repeats:
        logger.info("Skipped %d repeated handle(s).", repeats)
    return out


def _handles(handles: Iterable[str]) -> list[str]:
    return [e["handle"] for e in normalize_entries(handles)]


def read_handles(path: str | Path, column: str, *, delimiter: str | None = None) -> list[str]:
    """Read one column of a CSV or TSV file as handles."""
    source = Path(path)
    if delimiter is None:
        delimiter = "\t" if source.suffix.lower() in (".tsv", ".tab") else ","
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None or column not in reader.fieldnames:
            found = ", ".join(reader.fieldnames or [])
            raise ValueError(f"{source.name} has no column {column!r}. Columns: {found}")
        return [str(row[column]).strip() for row in reader if (row.get(column) or "").strip()]


class TagLists:
    """``client.tag_lists``."""

    def __init__(self, client: T3Client) -> None:
        self._client = client

    def list(
        self,
        *,
        license: str | None = None,
        visibility: Visibility | None = None,
        endpoint: str | None = None,
        archived: bool | None = None,
    ) -> builtins.list[dict[str, Any]]:
        """Every tag list you can see for a license (default: the client's), optionally narrowed."""
        query: dict[str, Any] = {"pageSize": 100}
        lic = license or self._client.license  # the spec marks licenseNumber required
        if lic:
            query["licenseNumber"] = lic
        if visibility:
            query["visibility"] = visibility
        if endpoint:
            query["t3EndpointId"] = endpoint
        if archived is not None:
            query["archived"] = "true" if archived else "false"
        return self._client._load_pages(BASE, query, label="tag lists", progress=False)

    def get(self, list_id: str) -> TagList:
        """Fetch one tag list by ID."""
        data = self._client._call("GET", _url(list_id))
        return TagList(self, _unwrap(data))

    def create(
        self,
        name: str,
        license: str | None = None,
        endpoint: str | None = None,
        visibility: Visibility = "USER",
        handles: Iterable[Entry] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> TagList:
        """Create a list, adding ``handles`` in chunks of 5,000."""
        lic = license or self._client.license
        if not lic:
            raise ValueError("create() needs license= (or a default license on the profile).")
        entries = normalize_entries(handles or [])
        body: dict[str, Any] = {"name": name, "licenseNumber": lic, "visibility": visibility}
        if endpoint:
            body["t3EndpointId"] = endpoint
        if metadata is not None:
            body["metadata"] = dict(metadata)
        if entries:
            body["entries"] = entries[:MAX_ENTRIES]
        tag_list = TagList(self, _unwrap(self._client._call("POST", BASE, json=body)))
        if len(entries) > MAX_ENTRIES:
            self.add(tag_list.id, entries[MAX_ENTRIES:])
            tag_list.refresh()
            logger.warning(
                "Tag list %r has %d entries. The server resolves lists of at most %d entries, "
                "so split it into smaller lists to use resolve().",
                name,
                len(entries),
                MAX_ENTRIES,
            )
        return tag_list

    def from_rows(
        self,
        rows: Iterable[Mapping[str, Any]],
        field: str,
        *,
        name: str,
        license: str | None = None,
        endpoint: str | None = None,
        visibility: Visibility = "USER",
    ) -> TagList:
        """Create a list from one field (dotted paths allowed) of each row."""
        handles = [str(v) for row in rows if (v := get_path(row, field)) not in (None, "")]
        return self.create(name, license=license, endpoint=endpoint, visibility=visibility, handles=handles)

    def from_csv(
        self,
        path: str | Path,
        column: str,
        *,
        name: str | None = None,
        license: str | None = None,
        endpoint: str | None = None,
        visibility: Visibility = "USER",
        delimiter: str | None = None,
    ) -> TagList:
        """Create a list from one column of a CSV or TSV file. ``name`` defaults to the file name."""
        handles = read_handles(path, column, delimiter=delimiter)
        return self.create(
            name or Path(path).stem,
            license=license,
            endpoint=endpoint,
            visibility=visibility,
            handles=handles,
        )

    def update(self, list_id: str, **fields: Any) -> TagList:
        """Change a list's fields (``name``, ``visibility``, ``metadata``, ``archived``...)."""
        data = self._client._call("PATCH", _url(list_id), json=fields)
        return TagList(self, _unwrap(data))

    def add(self, list_id: str, entries: Iterable[Entry]) -> dict[str, int]:
        """Add or update entries, 5,000 per request. Returns created and updated counts."""
        totals = {"created": 0, "updated": 0}
        for chunk in _chunks(normalize_entries(entries)):
            data = _unwrap(self._client._call("POST", _url(list_id, "/entries"), json={"entries": builtins.list(chunk)}))
            for key in totals:
                totals[key] += int(data.get(key) or 0)
        return totals

    def remove(self, list_id: str, handles: Iterable[str]) -> dict[str, Any]:
        """Remove entries, 5,000 per request. Returns counts and ``handlesNotFound``."""
        return self._batched("DELETE", list_id, "/entries", handles)

    def scan(self, list_id: str, handles: Iterable[str], scanned_at: str | None = None) -> dict[str, Any]:
        """Mark entries as scanned, 5,000 per request."""
        extra = {"scannedAt": scanned_at} if scanned_at else {}
        return self._batched("POST", list_id, "/scan", handles, extra)

    def _batched(
        self,
        method: str,
        list_id: str,
        suffix: str,
        handles: Iterable[str],
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for chunk in _chunks(_handles(handles)):
            data = _unwrap(
                self._client._call(method, _url(list_id, suffix), json={"handles": builtins.list(chunk), **(extra or {})})
            )
            for key, value in data.items():
                if isinstance(value, bool) or not isinstance(value, (int, list)):
                    merged[key] = value
                elif isinstance(value, int):
                    merged[key] = int(merged.get(key, 0)) + value
                else:
                    merged[key] = builtins.list(merged.get(key, [])) + value
        return merged

    def entries(self, list_id: str) -> builtins.list[dict[str, Any]]:
        """Every entry in the list."""
        return self._client._load_pages(
            _url(list_id, "/entries"), {"pageSize": 100}, label="tag list entries", progress=False
        )

    def resolve(
        self,
        list_id: str,
        endpoint: str | None = None,
        *,
        mask: str | Sequence[str] | None = None,
        include: Sequence[str] | None = None,
        progress: bool | None = None,
    ) -> builtins.list[dict[str, Any]]:
        """The objects the list's handles stand for, in the order they were added.

        ``endpoint`` is a collection's endpoint ID, such as
        ``METRC_ACTIVE_PACKAGES``; it defaults to the list's own. Raises
        :class:`~t3api_utils.errors.TagListResolveError` if any handle matches
        zero objects or several.
        """
        query: dict[str, Any] = {}
        if endpoint:
            query["t3EndpointId"] = endpoint
        if mask:
            query["collectionMask"] = mask if isinstance(mask, str) else ",".join(mask)
        if include:
            query["include"] = builtins.list(include)
        return self._client._load_pages(
            _url(list_id, "/resolve"), query, label="resolving tag list", progress=progress
        )


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        inner: dict[str, Any] = data["data"]
        return inner
    return data if isinstance(data, dict) else {}


class TagList:
    """One tag list, with the :class:`TagLists` methods bound to its ID."""

    def __init__(self, owner: TagLists, data: dict[str, Any]) -> None:
        self._owner = owner
        self.data = data

    @property
    def id(self) -> str:
        """The list's ID (a UUID)."""
        return str(self.data["id"])

    @property
    def name(self) -> str | None:
        """The list's name."""
        name = self.data.get("name")
        return None if name is None else str(name)

    @property
    def license(self) -> str | None:
        """The license the list belongs to."""
        lic = self.data.get("licenseNumber")
        return None if lic is None else str(lic)

    @property
    def endpoint(self) -> str | None:
        """The endpoint ID the list resolves against by default."""
        ep = self.data.get("t3EndpointId")
        return None if ep is None else str(ep)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __repr__(self) -> str:
        count = self.data.get("entryCount")
        return f"<TagList {self.id} {self.name!r} entries={count}>"

    def refresh(self) -> TagList:
        """Reload the list's fields from the server."""
        self.data = self._owner.get(self.id).data
        return self

    def update(self, **fields: Any) -> TagList:
        """Change the list's fields; see :meth:`TagLists.update`."""
        self.data = self._owner.update(self.id, **fields).data
        return self

    def add(self, entries: Iterable[Entry]) -> dict[str, int]:
        """Add or update entries; see :meth:`TagLists.add`."""
        return self._owner.add(self.id, entries)

    def remove(self, handles: Iterable[str]) -> dict[str, Any]:
        """Remove entries; see :meth:`TagLists.remove`."""
        return self._owner.remove(self.id, handles)

    def scan(self, handles: Iterable[str], scanned_at: str | None = None) -> dict[str, Any]:
        """Mark entries as scanned; see :meth:`TagLists.scan`."""
        return self._owner.scan(self.id, handles, scanned_at)

    def entries(self) -> list[dict[str, Any]]:
        """Every entry in the list."""
        return self._owner.entries(self.id)

    def resolve(
        self,
        endpoint: str | None = None,
        *,
        mask: str | Sequence[str] | None = None,
        include: Sequence[str] | None = None,
        progress: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve the list to its objects; see :meth:`TagLists.resolve`."""
        return self._owner.resolve(self.id, endpoint, mask=mask, include=include, progress=progress)
