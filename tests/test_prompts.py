"""t3.confirm(), t3.ask() and t3.choose(): public prompts for scripts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest

import t3api_utils as t3
from t3api_utils import _console, pickers, prompts
from t3api_utils.errors import NotInteractive


@dataclass
class Terminal:
    """Scripted answers for ``_console.ask`` and ``_console.confirm``."""

    answers: list[str] = field(default_factory=list)
    yes_no: list[bool] = field(default_factory=list)
    asked: list[tuple[str, str | None]] = field(default_factory=list)
    confirmed: list[tuple[str, bool]] = field(default_factory=list)

    def ask(
        self, text: str, *, default: str | None = None, password: bool = False, allow_empty: bool = False
    ) -> str:
        self.asked.append((text, default))
        if not self.answers:
            raise AssertionError(f"unexpected prompt {text!r}")
        return self.answers.pop(0)

    def confirm(self, text: str, *, default: bool = True) -> bool:
        self.confirmed.append((text, default))
        return self.yes_no.pop(0)


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> Terminal:
    fake = Terminal()
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    monkeypatch.setattr(_console, "ask", fake.ask)
    monkeypatch.setattr(_console, "confirm", fake.confirm)
    return fake


def test_exported_from_the_package() -> None:
    assert t3.confirm is prompts.confirm
    assert t3.ask is prompts.ask
    assert t3.choose is pickers.choose is prompts.choose


# --------------------------------------------------------------------------- confirm


def test_confirm_defaults_to_no(terminal: Terminal) -> None:
    terminal.yes_no = [True, False]
    assert t3.confirm("Submit 12 rows?") is True
    assert t3.confirm("Again?", default=True) is False
    assert terminal.confirmed == [("Submit 12 rows?", False), ("Again?", True)]


def test_confirm_without_a_terminal() -> None:
    with pytest.raises(NotInteractive, match=r"^The question 'Submit\?' needs a terminal to ask in\.$"):
        t3.confirm("Submit?")


# --------------------------------------------------------------------------- ask


def test_ask_returns_text(terminal: Terminal) -> None:
    terminal.answers = ["Room A"]
    assert t3.ask("Location", default="Vault") == "Room A"
    assert terminal.asked == [("Location", "Vault")]


def test_ask_parses_and_asks_again_on_value_error(
    terminal: Terminal, capsys: pytest.CaptureFixture[str]
) -> None:
    terminal.answers = ["lots", "12.5"]
    quantity: float = t3.ask("Quantity", parse=float)
    assert quantity == 12.5
    assert terminal.asked == [("Quantity", None), ("Quantity", None)]
    assert "✗ could not convert string to float: 'lots'" in capsys.readouterr().err


def test_ask_parses_dates(terminal: Terminal) -> None:
    terminal.answers = ["2026-11-23"]
    assert t3.ask("Date", default="2026-01-01", parse=date.fromisoformat) == date(2026, 11, 23)


def test_ask_value_error_without_a_message(terminal: Terminal, capsys: pytest.CaptureFixture[str]) -> None:
    def positive(text: str) -> int:
        value = int(text)
        if value <= 0:
            raise ValueError
        return value

    terminal.answers = ["-3", "4"]
    assert t3.ask("Count", parse=positive) == 4
    assert "✗ '-3' isn't valid." in capsys.readouterr().err


def test_ask_other_errors_propagate(terminal: Terminal) -> None:
    def broken(text: str) -> int:
        raise KeyError(text)

    terminal.answers = ["x"]
    with pytest.raises(KeyError):
        t3.ask("Thing", parse=broken)


def test_ask_without_a_terminal() -> None:
    with pytest.raises(NotInteractive, match=r"^The question 'Quantity' needs a terminal to ask in\.$"):
        t3.ask("Quantity", parse=float)


# --------------------------------------------------------------------------- choose


def test_choose_takes_columns_and_render_by_keyword(terminal: Terminal) -> None:
    terminal.answers = ["2"]
    packages = [{"label": "PKG-A"}, {"label": "PKG-B"}]
    chosen = t3.choose("Packages", packages, columns=["Label"], render=lambda p: [p["label"]])
    assert chosen == {"label": "PKG-B"}
    assert terminal.asked == [("Number", None)]


@pytest.mark.parametrize(("count", "prompt"), [(10, "Number"), (11, "Number, or text to filter")])
def test_choose_filters_long_lists_by_default(terminal: Terminal, count: int, prompt: str) -> None:
    terminal.answers = ["1"]
    t3.choose("Items", [f"item {i}" for i in range(count)], columns=["Item"], render=lambda i: [i])
    assert terminal.asked == [(prompt, None)]


def test_choose_filterable_can_be_forced_off(terminal: Terminal) -> None:
    terminal.answers = ["1"]
    t3.choose("Items", [str(i) for i in range(20)], ["Item"], lambda i: [i], filterable=False)
    assert terminal.asked == [("Number", None)]


def test_choose_without_a_terminal() -> None:
    with pytest.raises(NotInteractive, match="Items needs a terminal"):
        t3.choose("Items", ["a"], ["Item"], lambda i: [i])
