"""t3api-utils: secret-key auth, collections, reports and tag lists for the T3 API.

```python
import t3api_utils as t3

client = t3.connect()
items = client.collect("METRC_ACTIVE_ITEMS", license="LIC-00001")
t3.to_csv(items, "items.csv")
```

Importing the package has no side effects: no files, no logging setup, no
network calls.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import metadata
from typing import Any

from t3api_utils.auth.credentials import BearerAuth, SecretKeyAuth
from t3api_utils.auth.resolve import connect
from t3api_utils.client import T3Client
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
)
from t3api_utils.local import filter_rows, read_rows, to_csv, to_json
from t3api_utils.pickers import choose, pick_file
from t3api_utils.prompts import ask, confirm
from t3api_utils.spec.registry import Endpoint
from t3api_utils.tag_lists import TagList
from t3api_utils.writes import BulkResult, RowResult, WriteResult

try:
    __version__ = metadata.version("t3api-utils")
except metadata.PackageNotFoundError:  # pragma: no cover - only in odd installs
    __version__ = "0+unknown"

TUI_HINT = "t3.inspect() needs Textual. Install it with: pip install 't3api-utils[tui]'"


def inspect(rows: Sequence[Mapping[str, Any]], *, title: str = "rows") -> None:
    """Browse rows in the Textual inspector (needs ``t3api-utils[tui]``)."""
    try:
        from t3api_utils.tui import inspector
    except ImportError as exc:
        raise ImportError(TUI_HINT) from exc
    if not rows:
        from t3api_utils import _console

        _console.info("No rows to inspect.")
        return
    inspector.run(rows, title=title)


__all__ = [
    "APIError",
    "AuthError",
    "AuthRequired",
    "BearerAuth",
    "BulkResult",
    "Endpoint",
    "NotFound",
    "NotInteractive",
    "RateLimited",
    "RowResult",
    "SecretKeyAuth",
    "ServerError",
    "SpecError",
    "T3Client",
    "T3Error",
    "TagList",
    "TagListResolveError",
    "UnknownEndpoint",
    "ValidationError",
    "WriteResult",
    "__version__",
    "ask",
    "choose",
    "confirm",
    "connect",
    "filter_rows",
    "inspect",
    "pick_file",
    "read_rows",
    "to_csv",
    "to_json",
]
