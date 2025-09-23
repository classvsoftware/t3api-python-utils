"""Textual-based collection inspector application."""

import json
from typing import Any, Dict, Sequence

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, Static
from textual.containers import VerticalScroll
from textual.reactive import reactive

from t3api_utils.style import print_info


class JSONViewer(VerticalScroll):
    """A scrollable JSON viewer widget."""

    json_data: reactive[Dict[str, Any] | None] = reactive(None)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.can_focus = True
        self._content_static = Static(id="json-content")

    def on_mount(self) -> None:
        """Mount the content widget when the viewer is mounted."""
        self.mount(self._content_static)

    def watch_json_data(self, json_data: Dict[str, Any] | None) -> None:
        """Update displayed JSON when data changes."""
        if json_data is None:
            content = "⚠ No data available"
        else:
            # Format JSON with proper indentation
            formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
            content = formatted_json

        # Update content widget
        if hasattr(self, '_content_static'):
            self._content_static.update(content)


class SearchBar(Container):
    """Search input bar."""

    def compose(self) -> ComposeResult:
        """Create the search input."""
        yield Input(placeholder="🔍 Search data...", id="search-input")




class StatusBar(Static):
    """Status information display."""

    def __init__(self, collection_name: str, **kwargs: Any) -> None:
        self.collection_name = collection_name
        self.current_index = 0
        self.total_count = 0
        self.filtered_count = 0
        self.search_query = ""
        super().__init__(**kwargs)
        self.update_status()

    def update_status(self) -> None:
        """Update the status display."""
        position_text = f"{self.current_index + 1}/{self.filtered_count}" if self.filtered_count > 0 else "0/0"

        if self.search_query:
            search_text = f" | Search: '{self.search_query}' ({self.filtered_count}/{self.total_count})"
        else:
            search_text = ""

        status_text = f"Collection: {self.collection_name} | Position: {position_text}{search_text}"
        self.update(status_text)

    def set_position(self, current: int, filtered: int, total: int) -> None:
        """Update position information."""
        self.current_index = current
        self.filtered_count = filtered
        self.total_count = total
        self.update_status()

    def set_search(self, query: str, filtered_count: int) -> None:
        """Update search information."""
        self.search_query = query
        self.filtered_count = filtered_count
        self.update_status()


class CollectionInspectorApp(App[None]):
    """Textual app for inspecting collections."""

    CSS = """
    #main-container {
        height: 1fr;
        layout: vertical;
    }

    #content-area {
        height: 1fr;
        padding: 0;
        margin: 0;
    }

    #json-viewer {
        height: 100%;
        width: 100%;
        padding: 0;
        margin: 0;
    }

    #json-content {
        padding: 1;
        margin: 0;
    }

    #search-bar {
        height: auto;
        padding: 1;
        margin: 1;
    }

    #status {
        height: 1;
        padding: 0 1;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("left", "previous", "Previous", show=False),
        Binding("right", "next", "Next", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("ctrl+c", "clear", "Clear", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("slash", "focus_search", "Search", show=False),
        Binding("q,escape", "quit", "Quit"),
    ]

    def __init__(self, *, data: Sequence[Dict[str, Any]], collection_name: str = "collection") -> None:
        super().__init__()
        self.original_data = list(data)
        self.filtered_data = list(data)
        self.current_index = 0
        self.collection_name = collection_name
        self.search_query = ""

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()

        with Container(id="main-container"):
            yield StatusBar(self.collection_name, id="status")

            yield SearchBar(id="search-bar")

            with Container(id="content-area"):
                yield JSONViewer(id="json-viewer")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app when mounted."""
        self.title = f"Collection Inspector: {self.collection_name}"
        self.sub_title = f"{len(self.filtered_data)} objects"
        self._update_display()

    def _update_display(self) -> None:
        """Update the JSON viewer and status bar."""
        json_viewer = self.query_one("#json-viewer", JSONViewer)
        status_bar = self.query_one("#status", StatusBar)

        # Update JSON content
        if self.filtered_data and 0 <= self.current_index < len(self.filtered_data):
            current_obj = self.filtered_data[self.current_index]
            json_viewer.json_data = current_obj
        else:
            json_viewer.json_data = None

        # Update status
        status_bar.set_position(
            current=self.current_index,
            filtered=len(self.filtered_data),
            total=len(self.original_data)
        )

    def _object_contains_text(self, *, obj: Dict[str, Any], search_text: str) -> bool:
        """Recursively search object for text using case-insensitive matching."""
        search_lower = search_text.lower()

        def search_recursive(value: Any) -> bool:
            if isinstance(value, str):
                return search_lower in value.lower()
            elif isinstance(value, (int, float, bool)):
                return search_lower in str(value).lower()
            elif isinstance(value, dict):
                return any(search_recursive(v) for v in value.values())
            elif isinstance(value, list):
                return any(search_recursive(item) for item in value)
            return False

        return search_recursive(obj)

    def _apply_search_filter(self, *, query: str) -> None:
        """Apply search filter to data."""
        self.search_query = query.strip()

        if not self.search_query:
            self.filtered_data = self.original_data.copy()
        else:
            self.filtered_data = [
                obj for obj in self.original_data
                if self._object_contains_text(obj=obj, search_text=self.search_query)
            ]

        # Reset to first object after filter
        self.current_index = 0
        self._update_display()

    # Navigation actions
    def action_previous(self) -> None:
        """Navigate to previous object."""
        if self.filtered_data and self.current_index > 0:
            self.current_index -= 1
            self._update_display()

    def action_next(self) -> None:
        """Navigate to next object."""
        if self.filtered_data and self.current_index < len(self.filtered_data) - 1:
            self.current_index += 1
            self._update_display()

    def action_first(self) -> None:
        """Navigate to first object."""
        if self.filtered_data:
            self.current_index = 0
            self._update_display()

    def action_last(self) -> None:
        """Navigate to last object."""
        if self.filtered_data:
            self.current_index = len(self.filtered_data) - 1
            self._update_display()


    def action_clear(self) -> None:
        """Clear search filter."""
        search_input = self.query_one("#search-input", Input)
        search_input.value = ""
        self._apply_search_filter(query="")
        status_bar = self.query_one("#status", StatusBar)
        status_bar.set_search("", len(self.filtered_data))

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()

    def action_help(self) -> None:
        """Show help information."""
        help_text = """ℹ Navigation: ←/→-Previous/Next Home/End-First/Last Ctrl+C-Clear /-Search ?-Help q/Esc-Quit. Use search bar to filter data."""
        self.notify(help_text, severity="information")

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        self._apply_search_filter(query=event.value)
        status_bar = self.query_one("#status", StatusBar)
        status_bar.set_search(self.search_query, len(self.filtered_data))


def inspect_collection(*, data: Sequence[Dict[str, Any]], collection_name: str = "collection") -> None:
    """Launch the Textual collection inspector."""
    if not data:
        print_info("No data to inspect")
        return

    app = CollectionInspectorApp(data=data, collection_name=collection_name)
    app.run()