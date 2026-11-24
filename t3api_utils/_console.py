"""Rich consoles, the purple theme and small message helpers (internal).

Messages and prompts go to stderr so that stdout stays clean for data.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.console import Console, RenderableType
from rich.markup import escape
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.style import StyleType
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from t3api_utils.errors import NotInteractive

THEME = Theme(
    {
        "primary": "#8B5CF6",
        "accent": "#A855F7",
        "muted": "#C4B5FD",
        "bright": "#DDD6FE",
        "success": "#10B981",
        "error": "#EF4444",
        "warning": "#F59E0B",
        "info": "#6366F1",
    }
)

console = Console(theme=THEME, stderr=True, highlight=False)
"""Status messages, prompts, tables shown to a person. Writes to stderr."""

out = Console(theme=THEME, highlight=False)
"""Data meant for stdout (e.g. `t3api whoami`, printed URLs)."""


def is_interactive() -> bool:
    """True when a person can answer prompts: a terminal, or a Jupyter kernel."""
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return True
    except (AttributeError, ValueError):
        pass
    return _in_jupyter()


def _in_jupyter() -> bool:
    shell = sys.modules.get("IPython")
    if shell is None:
        return False
    get_ipython = getattr(shell, "get_ipython", None)
    if get_ipython is None:
        return False
    ip = get_ipython()
    return ip is not None and type(ip).__name__ == "ZMQInteractiveShell"


def stderr_is_terminal() -> bool:
    return console.is_terminal


def success(message: str) -> None:
    console.print(f"[bold green]✓[/bold green] {escape(message)}")


def error(message: str) -> None:
    console.print(f"[bold red]✗[/bold red] {escape(message)}")


def warning(message: str) -> None:
    console.print(f"[bold yellow]⚠[/bold yellow] {escape(message)}")


def info(message: str) -> None:
    console.print(f"[bold blue]ℹ[/bold blue] {escape(message)}")


def progress(message: str) -> None:
    console.print(f"[bold magenta]⋯[/bold magenta] {escape(message)}")


def header(title: str) -> None:
    console.print(f"[bold magenta]═══ {escape(title)} ═══[/bold magenta]")


class _PlainTable(Table):
    """A Table whose string cells are shown as written, not parsed as Rich markup.

    Cells hold data (names, messages, paths) that may contain ``[...]``.
    """

    def add_row(
        self,
        *renderables: RenderableType | None,
        style: StyleType | None = None,
        end_section: bool = False,
    ) -> None:
        cells = [Text(cell) if isinstance(cell, str) else cell for cell in renderables]
        super().add_row(*cells, style=style, end_section=end_section)


def table(title: str | None = None) -> Table:
    """A table in the house style (magenta borders and headers)."""
    return _PlainTable(title=title, border_style="magenta", header_style="bold magenta")


def mask_secret(value: str | None, keep: int = 4) -> str:
    """Show only the last few characters of a secret."""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * 8 + value[-keep:]


def require_interactive(what: str) -> None:
    if not is_interactive():
        raise NotInteractive(f"{what} needs a terminal to ask in.")


def ask(
    text: str,
    *,
    default: str | None = None,
    password: bool = False,
    allow_empty: bool = False,
) -> str:
    """Prompt for text. Raises NotInteractive without a terminal."""
    require_interactive("This prompt")
    while True:
        if default is None:
            value = Prompt.ask(f"[magenta]{escape(text)}[/magenta]", console=console, password=password)
        else:
            value = Prompt.ask(
                f"[magenta]{escape(text)}[/magenta]", console=console, password=password, default=default
            )
        value = (value or "").strip()
        if value or allow_empty:
            return value
        error("A value is required.")


def confirm(text: str, *, default: bool = True) -> bool:
    """Ask a yes/no question. Raises NotInteractive without a terminal."""
    require_interactive("This prompt")
    return bool(Confirm.ask(f"[magenta]{escape(text)}[/magenta]", console=console, default=default))


@contextmanager
def progress_bar(label: str, total: int | None, enabled: bool) -> Iterator[Callable[[int], None]]:
    """Yields ``advance(n)``. Shows a transient Rich progress bar when enabled."""
    if not enabled:

        def ignore(n: int = 1) -> None:
            return None

        yield ignore
        return
    with Progress(
        SpinnerColumn(style="magenta"),
        TextColumn("[magenta]{task.description}"),
        BarColumn(complete_style="magenta", finished_style="green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as bar:
        task = bar.add_task(label, total=total)

        def advance(n: int = 1) -> None:
            bar.advance(task, n)

        yield advance
