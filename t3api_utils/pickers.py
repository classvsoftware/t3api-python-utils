"""Interactive pickers shown as Rich tables.

Without a terminal they raise :class:`~t3api_utils.errors.NotInteractive`.
Ctrl-C raises ``KeyboardInterrupt`` to the caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeVar

from t3api_utils import _console
from t3api_utils.spec.registry import Endpoint

T = TypeVar("T")

PAGE = 40
DEFAULT_FILE_PATTERNS = ("*.csv", "*.tsv", "*.json", "*.jsonl")


def choose(
    title: str,
    items: Sequence[T],
    columns: Sequence[str],
    render: Any,
    *,
    filterable: bool = False,
) -> T:
    """Show ``items`` as a numbered table and return the chosen one.

    ``render(item)`` returns one string per column after the number. With
    ``filterable=True``, typing text instead of a number narrows the list.
    """
    if not items:
        raise ValueError(f"{title}: nothing to choose from.")
    _console.require_interactive(title)
    shown: list[T] = list(items)
    while True:
        table = _console.table(title)
        table.add_column("#", style="magenta", justify="right")
        for i, name in enumerate(columns):
            table.add_column(name, style="bright_white" if i == 0 else "cyan")
        for number, item in enumerate(shown[:PAGE], 1):
            table.add_row(str(number), *render(item))
        _console.console.print(table)
        if len(shown) > PAGE:
            _console.info(f"Showing {PAGE} of {len(shown)}. Type text to narrow the list.")
        prompt = "Number, or text to filter" if filterable else "Number"
        answer = _console.ask(prompt)
        if answer.isdecimal():
            index = int(answer)
            if 1 <= index <= min(len(shown), PAGE):
                return shown[index - 1]
            _console.error(f"Pick a number from 1 to {min(len(shown), PAGE)}.")
            continue
        if not filterable:
            _console.error("Type a number.")
            continue
        words = answer.lower().split()
        narrowed = [
            item for item in items if all(w in " ".join(render(item)).lower() for w in words)
        ]
        if not narrowed:
            _console.error(f"Nothing matches {answer!r}.")
            shown = list(items)
        else:
            shown = narrowed


def pick_license(licenses: Sequence[dict[str, Any]]) -> str:
    """Pick one license; returns its license number."""
    if len(licenses) == 1:
        number = str(licenses[0].get("licenseNumber"))
        _console.info(f"Using the only license available: {number}")
        return number
    chosen = choose(
        "Licenses",
        licenses,
        ["License", "Name"],
        lambda lic: [str(lic.get("licenseNumber", "")), str(lic.get("licenseName", ""))],
        filterable=len(licenses) > 10,
    )
    return str(chosen.get("licenseNumber"))


def pick_endpoint(endpoints: Sequence[Endpoint]) -> Endpoint:
    """Pick one endpoint from the spec. Typing text narrows the list."""
    return choose(
        "Endpoints",
        sorted(endpoints, key=lambda ep: (ep.id or "~", ep.path)),
        ["Endpoint", "Path", "Summary"],
        lambda ep: [ep.id or "", f"{ep.method} {ep.path}", ep.summary],
        filterable=True,
    )


def pick_file(
    directory: str | Path = ".",
    *,
    patterns: Sequence[str] = DEFAULT_FILE_PATTERNS,
    title: str = "Files",
) -> Path:
    """Pick a file from ``directory`` (newest first), or type a path."""
    _console.require_interactive(title)
    folder = Path(directory)
    files = sorted(
        {p for pattern in patterns for p in folder.glob(pattern) if p.is_file()},
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        _console.info(f"No {', '.join(patterns)} files in {folder.resolve()}.")
        while True:
            typed = Path(_console.ask("Path to the file")).expanduser()
            if typed.is_file():
                return typed
            _console.error(f"{typed} isn't a file.")
    return choose(
        title,
        files,
        ["File", "Size"],
        lambda p: [p.name, f"{p.stat().st_size:,} bytes"],
        filterable=True,
    )
