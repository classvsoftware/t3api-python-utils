"""The Textual row inspector, driven with Textual's pilot."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Input, Static

from t3api_utils.tui import inspector
from t3api_utils.tui.inspector import HELP, InspectorApp, contains_text

ROWS: list[dict[str, Any]] = [
    {"id": 1, "name": "Alpha", "tags": ["indoor", {"room": "North"}], "weight": 3.5},
    {"id": 2, "name": "Beta", "active": True, "item": {"category": "Flower"}},
    {"id": 3, "name": "Gamma", "note": None, "pair": ("x", "y")},
]

Scenario = Callable[[InspectorApp, Pilot[None]], Awaitable[None]]


def drive(rows: Sequence[Mapping[str, Any]], scenario: Scenario, *, title: str = "rows") -> InspectorApp:
    app = InspectorApp(rows, title=title)

    async def main() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await scenario(app, pilot)

    asyncio.run(main())
    return app


def status(app: InspectorApp) -> str:
    return str(app.query_one("#status", Static).content)


def content(app: InspectorApp) -> str:
    return str(app.query_one("#content", Static).content)


def shown(app: InspectorApp) -> Any:
    return json.loads(content(app))


# --------------------------------------------------------------------------- contains_text


@pytest.mark.parametrize(
    ("value", "needle", "found"),
    [
        ("Blue Dream", "dream", True),
        ("Blue Dream", "kush", False),
        (42, "42", True),
        (3.5, "3.5", True),
        (True, "true", True),
        (False, "true", False),
        ({"item": {"name": "OG Kush"}}, "kush", True),
        ({"kush": "key only"}, "kush", False),
        (["a", ["b", {"c": "deep"}]], "deep", True),
        (("x", "y"), "y", True),
        ([], "x", False),
        (None, "none", False),
        (date(2026, 1, 1), "2026", False),
    ],
)
def test_contains_text(value: Any, needle: str, found: bool) -> None:
    assert contains_text(value, needle) is found


# --------------------------------------------------------------------------- the app


def test_mount_shows_the_first_row() -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        assert app.title == "t3api inspector · METRC_ACTIVE_ITEMS"
        assert app.sub_title == "3 rows"
        assert app.focused is app.query_one("#viewer")
        assert status(app) == "Row 1/3"
        assert shown(app) == ROWS[0]
        assert content(app) == json.dumps(ROWS[0], indent=2, ensure_ascii=False)

    drive(ROWS, scenario, title="METRC_ACTIVE_ITEMS")


def test_arrow_keys_move_between_rows_and_stop_at_the_ends() -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        await pilot.press("left")
        assert app.index == 0
        await pilot.press("right")
        assert (app.index, status(app), shown(app)["name"]) == (1, "Row 2/3", "Beta")
        await pilot.press("right", "right", "right")
        assert (app.index, status(app)) == (2, "Row 3/3")
        await pilot.press("left")
        assert shown(app)["name"] == "Beta"

    drive(ROWS, scenario)


def test_home_and_end_jump_to_first_and_last() -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        await pilot.press("end")
        assert (app.index, shown(app)["name"]) == (2, "Gamma")
        await pilot.press("home")
        assert (app.index, shown(app)["name"]) == (0, "Alpha")

    drive(ROWS, scenario)


def test_home_and_end_still_jump_when_a_row_is_taller_than_the_screen() -> None:
    tall = [{"row": n, **{f"field_{i:03d}": i for i in range(120)}} for n in range(3)]

    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        viewer = app.query_one("#viewer")
        assert viewer.max_scroll_y > 0
        await pilot.press("end")
        assert app.index == 2
        await pilot.press("home")
        assert app.index == 0
        await pilot.press("pagedown")
        await pilot.pause()
        assert app.index == 0
        assert viewer.scroll_y > 0  # other keys still scroll the row

    drive(tall, scenario)


def test_typing_in_search_filters_rows() -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        await pilot.press("slash")
        assert app.focused is app.query_one("#search", Input)
        await pilot.press(*"flower")
        assert app.rows == [ROWS[1]]
        assert status(app) == "Row 1/1 · 1 of 3 match 'flower'"
        assert shown(app)["name"] == "Beta"

    drive(ROWS, scenario)


@pytest.mark.parametrize(
    ("query", "names"),
    [
        ("north", ["Alpha"]),  # dict inside a list
        ("3.5", ["Alpha"]),  # float
        ("true", ["Beta"]),  # bool
        ("A", ["Alpha", "Beta", "Gamma"]),  # case-insensitive
        ("  gamma  ", ["Gamma"]),  # trimmed
        ("y", ["Gamma"]),  # tuple
        ("", ["Alpha", "Beta", "Gamma"]),
    ],
)
def test_search_matches_nested_values(query: str, names: list[str]) -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        await pilot.press("right")
        app.apply_search(query)
        assert [r["name"] for r in app.rows] == names
        assert app.index == 0
        assert app.query_text == query.strip()

    drive(ROWS, scenario)


def test_no_matches() -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        app.apply_search("zzz")
        await pilot.pause()
        assert content(app) == "No rows match."
        assert status(app) == "Row 0/0 · 0 of 3 match 'zzz'"
        app.action_next()
        app.action_previous()
        app.action_last()
        assert app.index == 0
        app.action_first()
        assert content(app) == "No rows match."

    drive(ROWS, scenario)


def test_ctrl_l_clears_the_search_and_returns_to_the_viewer() -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        await pilot.press("slash", *"beta")
        assert len(app.rows) == 1
        await pilot.press("ctrl+l")
        assert app.query_one("#search", Input).value == ""
        assert app.rows == ROWS
        assert app.query_text == ""
        assert status(app) == "Row 1/3"
        assert app.focused is app.query_one("#viewer")

    drive(ROWS, scenario)


def test_question_mark_shows_the_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    notes: list[tuple[str, dict[str, Any]]] = []

    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append((message, kwargs)))
        await pilot.press("question_mark")

    drive(ROWS, scenario)
    assert notes == [(HELP, {"title": "Keys"})]


@pytest.mark.parametrize("key", ["q", "escape"])
def test_quit_keys(key: str) -> None:
    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        await pilot.press(key)
        await pilot.pause()
        assert not app.is_running

    drive(ROWS, scenario)


def test_values_json_cannot_encode_are_shown_as_text() -> None:
    rows = [{"when": date(2026, 1, 2), "label": "café"}]

    async def scenario(app: InspectorApp, pilot: Pilot[None]) -> None:
        assert shown(app) == {"when": "2026-01-02", "label": "café"}

    drive(rows, scenario)


def test_rows_are_copied() -> None:
    rows = list(ROWS)
    app = InspectorApp(rows)
    rows.clear()
    assert app.all_rows == ROWS
    assert app.rows == ROWS
    assert app.rows is not app.all_rows
    assert app.inspector_title == "rows"


def test_run_starts_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[InspectorApp] = []

    def fake_run(self: InspectorApp, **kwargs: Any) -> None:
        started.append(self)

    monkeypatch.setattr(InspectorApp, "run", fake_run)
    inspector.run(ROWS, title="packages")
    [app] = started
    assert app.all_rows == ROWS
    assert app.inspector_title == "packages"
