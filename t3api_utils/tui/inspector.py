"""The Textual row inspector (needs the ``tui`` extra: ``pip install 't3api-utils[tui]'``).

Browse rows one at a time as formatted JSON, with live search across every
nested value. Import this module only through :func:`t3api_utils.inspect`, so
Textual is loaded only when it is used.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.widgets import Footer, Header, Input, Static

HELP = (
    "←/→ previous/next · Home/End first/last · / search · Ctrl+L clear search · "
    "? help · q or Esc quit"
)


def contains_text(value: Any, needle: str) -> bool:
    """Case-insensitive search through every nested value."""
    if isinstance(value, str):
        return needle in value.lower()
    if isinstance(value, (bool, int, float)):
        return needle in str(value).lower()
    if isinstance(value, Mapping):
        return any(contains_text(v, needle) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_text(v, needle) for v in value)
    return False


class _Viewer(VerticalScroll):
    """The JSON pane. Home and End pick the first and last row, as the help says,
    instead of scrolling within a row that is taller than the screen."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("home", "app.first", "First", show=False),
        Binding("end", "app.last", "Last", show=False),
    ]


class InspectorApp(App[None]):
    """Browse rows as JSON, one at a time."""

    CSS = """
    #search { margin: 0 1; }
    #status { height: 1; padding: 0 1; color: $accent; }
    #viewer { height: 1fr; }
    #content { padding: 1 2; }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "previous", "Previous"),
        Binding("right", "next", "Next"),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("slash", "focus_search", "Search"),
        Binding("ctrl+l", "clear", "Clear search"),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q,escape", "quit", "Quit"),
    ]

    def __init__(self, rows: Sequence[Mapping[str, Any]], *, title: str = "rows") -> None:
        super().__init__()
        self.all_rows = list(rows)
        self.rows = list(rows)
        self.index = 0
        self.query_text = ""
        self.inspector_title = title

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Input(placeholder="Search every field…", id="search")
            yield Static(id="status")
            with _Viewer(id="viewer"):
                yield Static(id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"t3api inspector · {self.inspector_title}"
        self.sub_title = f"{len(self.all_rows)} rows"
        self.query_one("#viewer").focus()
        self.refresh_view()

    def status_text(self) -> str:
        position = f"{self.index + 1}/{len(self.rows)}" if self.rows else "0/0"
        text = f"Row {position}"
        if self.query_text:
            text += f" · {len(self.rows)} of {len(self.all_rows)} match {self.query_text!r}"
        return text

    def refresh_view(self) -> None:
        content = self.query_one("#content", Static)
        if self.rows:
            content.update(json.dumps(self.rows[self.index], indent=2, ensure_ascii=False, default=str))
        else:
            content.update("No rows match.")
        self.query_one("#status", Static).update(self.status_text())

    def apply_search(self, text: str) -> None:
        self.query_text = text.strip()
        needle = self.query_text.lower()
        self.rows = [r for r in self.all_rows if contains_text(r, needle)] if needle else list(self.all_rows)
        self.index = 0
        self.refresh_view()

    @on(Input.Changed, "#search")
    def on_search_changed(self, event: Input.Changed) -> None:
        self.apply_search(event.value)

    def action_previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self.refresh_view()

    def action_next(self) -> None:
        if self.index < len(self.rows) - 1:
            self.index += 1
            self.refresh_view()

    def action_first(self) -> None:
        self.index = 0
        self.refresh_view()

    def action_last(self) -> None:
        self.index = max(0, len(self.rows) - 1)
        self.refresh_view()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear(self) -> None:
        self.query_one("#search", Input).value = ""
        self.apply_search("")
        self.query_one("#viewer").focus()

    def action_help(self) -> None:
        self.notify(HELP, title="Keys")


def run(rows: Sequence[Mapping[str, Any]], *, title: str = "rows") -> None:
    InspectorApp(rows, title=title).run()
