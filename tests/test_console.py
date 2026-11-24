"""t3api_utils._console: terminal detection, prompts, messages, tables, progress."""

from __future__ import annotations

import io
import sys
import types
from collections.abc import Callable
from typing import Any

import pytest
from rich.console import Console
from rich.progress import Progress, TaskID
from rich.prompt import Confirm, Prompt
from rich.text import Text

from t3api_utils import _console
from t3api_utils.errors import NotInteractive

# Captured at import (collection) time, before the autouse fixture replaces it.
REAL_IS_INTERACTIVE: Callable[[], bool] = _console.is_interactive


@pytest.fixture(autouse=True)
def wide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    for name in ("FORCE_COLOR", "TTY_COMPATIBLE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_console, "is_interactive", lambda: True)


class FakeStdin:
    def __init__(self, tty: bool | Exception) -> None:
        self.tty = tty

    def isatty(self) -> bool:
        if isinstance(self.tty, Exception):
            raise self.tty
        return self.tty


def fake_ipython(monkeypatch: pytest.MonkeyPatch, shell_class: str | None, *, has_getter: bool = True) -> None:
    module = types.ModuleType("IPython")
    if has_getter:
        shell = None if shell_class is None else type(shell_class, (), {})()
        module.get_ipython = lambda: shell  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "IPython", module)


# --------------------------------------------------------------------------- is_interactive


def test_captured_the_real_function() -> None:
    assert REAL_IS_INTERACTIVE.__module__ == "t3api_utils._console"
    assert REAL_IS_INTERACTIVE.__name__ == "is_interactive"


def test_terminal_stdin_is_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", FakeStdin(True))
    assert REAL_IS_INTERACTIVE() is True


@pytest.mark.parametrize(
    "stdin",
    [FakeStdin(False), None, FakeStdin(ValueError("I/O operation on closed file")), object()],
    ids=["not-a-tty", "none", "closed", "no-isatty"],
)
def test_no_terminal_and_no_jupyter(monkeypatch: pytest.MonkeyPatch, stdin: object) -> None:
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.delitem(sys.modules, "IPython", raising=False)
    assert REAL_IS_INTERACTIVE() is False


def test_jupyter_kernel_is_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", FakeStdin(False))
    fake_ipython(monkeypatch, "ZMQInteractiveShell")
    assert REAL_IS_INTERACTIVE() is True


def test_jupyter_detected_even_when_stdin_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", FakeStdin(ValueError("closed")))
    fake_ipython(monkeypatch, "ZMQInteractiveShell")
    assert REAL_IS_INTERACTIVE() is True


@pytest.mark.parametrize(
    ("shell_class", "has_getter"),
    [("TerminalInteractiveShell", True), (None, True), (None, False)],
    ids=["ipython-terminal", "no-shell", "no-get_ipython"],
)
def test_other_ipython_setups_are_not_jupyter(
    monkeypatch: pytest.MonkeyPatch, shell_class: str | None, has_getter: bool
) -> None:
    monkeypatch.setattr(sys, "stdin", FakeStdin(False))
    fake_ipython(monkeypatch, shell_class, has_getter=has_getter)
    assert REAL_IS_INTERACTIVE() is False


def test_require_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(NotInteractive, match=r"^Picking a file needs a terminal to ask in\.$"):
        _console.require_interactive("Picking a file")
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    _console.require_interactive("Picking a file")


@pytest.mark.parametrize("forced", [True, False])
def test_stderr_is_terminal(monkeypatch: pytest.MonkeyPatch, forced: bool) -> None:
    monkeypatch.setattr(_console, "console", Console(force_terminal=forced))
    assert _console.stderr_is_terminal() is forced


def test_consoles_split_stdout_and_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _console.console.print("for people")
    _console.out.print("for pipes")
    captured = capsys.readouterr()
    assert captured.err == "for people\n"
    assert captured.out == "for pipes\n"


# --------------------------------------------------------------------------- messages


@pytest.mark.parametrize(
    ("helper", "symbol"),
    [
        (_console.success, "✓"),
        (_console.error, "✗"),
        (_console.warning, "⚠"),
        (_console.info, "ℹ"),
        (_console.progress, "⋯"),
    ],
)
def test_message_helpers(
    capsys: pytest.CaptureFixture[str], helper: Callable[[str], None], symbol: str
) -> None:
    helper("Saved 3 rows")
    assert capsys.readouterr().err == f"{symbol} Saved 3 rows\n"


def test_messages_show_brackets_literally(capsys: pytest.CaptureFixture[str]) -> None:
    _console.error("It has [report]; see [/v2/items] and [bold]x[/bold]")
    assert capsys.readouterr().err == "✗ It has [report]; see [/v2/items] and [bold]x[/bold]\n"


def test_header(capsys: pytest.CaptureFixture[str]) -> None:
    _console.header("T3 login · profile [main]")
    assert capsys.readouterr().err == "═══ T3 login · profile [main] ═══\n"


# --------------------------------------------------------------------------- table


def render(table: Any) -> str:
    recorder = Console(record=True, width=120, file=io.StringIO())
    recorder.print(table)
    return recorder.export_text()


def test_table_house_style() -> None:
    table = _console.table("Profiles")
    assert table.title == "Profiles"
    assert table.border_style == "magenta"
    assert table.header_style == "bold magenta"
    assert _console.table().title is None


def test_table_cells_are_plain_text() -> None:
    table = _console.table("Tag lists")
    table.add_column("#", justify="right")
    table.add_column("Name")
    table.add_row("1", "Room [A] [/b] [bold]c")
    styled = Text("kept", style="bold")
    table.add_row("10", styled, end_section=True)
    table.add_row("11", None, style="dim")
    text = render(table)
    assert "Room [A] [/b] [bold]c" in text
    assert "kept" in text
    assert table.rows[1].end_section is True
    assert table.rows[2].style == "dim"
    # Renderables other than str pass through untouched.
    assert table.columns[1]._cells[1] is styled


# --------------------------------------------------------------------------- mask_secret


@pytest.mark.parametrize(
    ("value", "keep", "masked"),
    [
        (None, 4, ""),
        ("", 4, ""),
        ("abc", 4, "***"),
        ("abcd", 4, "****"),
        ("abcdefgh", 4, "********efgh"),
        ("a-very-long-secret-key", 4, "********-key"),
        ("abcdefgh", 2, "********gh"),
    ],
)
def test_mask_secret(value: str | None, keep: int, masked: str) -> None:
    assert _console.mask_secret(value, keep=keep) == masked


# --------------------------------------------------------------------------- ask / confirm


class FakePrompt:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs))
        return self.answers.pop(0)


def test_ask_without_terminal() -> None:
    with pytest.raises(NotInteractive, match="This prompt needs a terminal"):
        _console.ask("Name")


@pytest.mark.usefixtures("terminal")
def test_ask_strips_and_has_no_default(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePrompt("  jane  ")
    monkeypatch.setattr(Prompt, "ask", fake)
    assert _console.ask("Metrc username") == "jane"
    [(prompt, kwargs)] = fake.calls
    assert prompt == "[magenta]Metrc username[/magenta]"
    assert kwargs == {"console": _console.console, "password": False}


@pytest.mark.usefixtures("terminal")
def test_ask_with_default_and_password(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePrompt("ca.metrc.com")
    monkeypatch.setattr(Prompt, "ask", fake)
    assert _console.ask("Metrc hostname", default="ca.metrc.com", password=True) == "ca.metrc.com"
    [(_, kwargs)] = fake.calls
    assert kwargs == {"console": _console.console, "password": True, "default": "ca.metrc.com"}


@pytest.mark.usefixtures("terminal")
def test_ask_repeats_until_answered(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakePrompt("   ", None, "value")
    monkeypatch.setattr(Prompt, "ask", fake)
    assert _console.ask("Name") == "value"
    assert len(fake.calls) == 3
    assert capsys.readouterr().err.count("✗ A value is required.") == 2


@pytest.mark.usefixtures("terminal")
def test_ask_allow_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Prompt, "ask", FakePrompt("  "))
    assert _console.ask("Optional note", allow_empty=True) == ""


@pytest.mark.usefixtures("terminal")
def test_ask_escapes_brackets_in_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePrompt("x")
    monkeypatch.setattr(Prompt, "ask", fake)
    _console.ask("Path [optional]")
    assert fake.calls[0][0] == "[magenta]Path \\[optional][/magenta]"


def test_confirm_without_terminal() -> None:
    with pytest.raises(NotInteractive):
        _console.confirm("Continue?")


@pytest.mark.usefixtures("terminal")
@pytest.mark.parametrize(("answer", "default"), [(True, True), (False, False), (1, True)])
def test_confirm(monkeypatch: pytest.MonkeyPatch, answer: Any, default: bool) -> None:
    fake = FakePrompt(answer)
    monkeypatch.setattr(Confirm, "ask", fake)
    assert _console.confirm("Save it [now]?", default=default) is bool(answer)
    [(prompt, kwargs)] = fake.calls
    assert prompt == "[magenta]Save it \\[now]?[/magenta]"
    assert kwargs == {"console": _console.console, "default": default}


# --------------------------------------------------------------------------- progress_bar


def test_progress_bar_disabled_draws_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_progress(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Progress should not be created")

    monkeypatch.setattr(_console, "Progress", no_progress)
    with _console.progress_bar("Loading", 10, enabled=False) as advance:
        assert advance(3) is None
        assert advance(1) is None


def test_progress_bar_enabled_advances_a_task(monkeypatch: pytest.MonkeyPatch) -> None:
    bars: list[SpyProgress] = []

    class SpyProgress(Progress):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.advanced: list[float] = []
            bars.append(self)

        def advance(self, task_id: TaskID, advance: float = 1) -> None:
            self.advanced.append(advance)
            super().advance(task_id, advance)

    monkeypatch.setattr(_console, "Progress", SpyProgress)
    with _console.progress_bar("Loading pages", 3, enabled=True) as advance:
        advance(1)
        advance(2)
    [bar] = bars
    assert bar.advanced == [1, 2]
    [task] = bar.tasks
    assert task.description == "Loading pages"
    assert task.total == 3
    assert task.completed == 3
    assert bar.live.transient is True
    assert bar.console is _console.console


def test_progress_bar_with_an_unknown_total(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Progress] = []

    def capture(*args: Any, **kwargs: Any) -> Progress:
        bar = Progress(*args, **kwargs)
        seen.append(bar)
        return bar

    monkeypatch.setattr(_console, "Progress", capture)
    with _console.progress_bar("Pages", None, enabled=True) as advance:
        advance(1)
        advance(1)
    assert seen[0].tasks[0].completed == 2
    assert seen[0].tasks[0].total is None
