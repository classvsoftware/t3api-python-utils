"""The ``t3api`` root: --version, --verbose, help, and error handling."""

from __future__ import annotations

import logging

import pytest
from rich.logging import RichHandler

import t3api_utils as t3
import t3api_utils.cli
from t3api_utils.auth.store import Store
from t3api_utils.errors import NotInteractive, T3Error
from tests._cli_helpers import cli_app, invoke
from tests._cli_helpers import cli_env  # noqa: F401  (fixture)


def test_package_exposes_the_typer_app() -> None:
    assert t3api_utils.cli.app is cli_app.app


def test_version_prints_to_stdout() -> None:
    result = invoke("--version")
    assert result.exit_code == 0
    assert result.stdout == f"t3api-utils {t3.__version__}\n"
    assert result.stderr == ""


def test_no_arguments_shows_help() -> None:
    result = invoke()
    assert result.exit_code in (0, 2)  # click >= 8.2 exits 2 for no_args_is_help
    for command in ("login", "logout", "pull", "report", "tag-lists", "spec"):
        assert command in result.output


def test_rich_handler_installed_once_and_level_follows_verbose() -> None:
    logger = logging.getLogger("t3api_utils")

    assert invoke("--verbose", "profiles", "list").exit_code == 0
    assert logger.level == logging.INFO
    assert logger.propagate is False
    assert sum(isinstance(h, RichHandler) for h in logger.handlers) == 1

    assert invoke("profiles", "list").exit_code == 0
    assert logger.level == logging.WARNING
    assert sum(isinstance(h, RichHandler) for h in logger.handlers) == 1


@pytest.mark.parametrize(
    ("exc", "message"),
    [
        (T3Error("boom"), "boom"),
        (NotInteractive("Licenses needs a terminal to ask in."), "Licenses needs a terminal to ask in."),
        (ValueError("bad value"), "bad value"),
        (KeyError("No profile named 'x'."), "No profile named 'x'."),
        (FileNotFoundError("nope.csv"), "nope.csv"),
        (ImportError("needs textual"), "needs textual"),
    ],
)
def test_library_errors_become_a_red_message_and_exit_1(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, message: str
) -> None:
    def broken() -> Store:
        raise exc

    monkeypatch.setattr(cli_app, "_store", broken)
    result = invoke("profiles", "list")
    assert result.exit_code == 1
    assert result.stderr == f"✗ {message}\n"
    assert result.stdout == ""


def test_key_error_shows_its_message_not_its_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> Store:
        raise KeyError("missing")

    monkeypatch.setattr(cli_app, "_store", broken)
    result = invoke("profiles", "list")
    assert "✗ missing" in result.stderr
    assert "'missing'" not in result.stderr


def test_error_text_with_brackets_is_shown_literally(monkeypatch: pytest.MonkeyPatch) -> None:
    # Server details and spec errors contain brackets; they must not be read as Rich markup.
    def broken() -> Store:
        raise T3Error("It has: GET /v2/items/report [report]; see [/v2/items] and [bold]x")

    monkeypatch.setattr(cli_app, "_store", broken)
    result = invoke("profiles", "list")
    assert result.exit_code == 1
    assert "It has: GET /v2/items/report [report]; see [/v2/items] and [bold]x" in result.stderr


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, EOFError], ids=["ctrl-c", "ctrl-d"])
def test_interrupt_exits_130(monkeypatch: pytest.MonkeyPatch, interruption: type[BaseException]) -> None:
    def interrupted() -> Store:
        raise interruption

    monkeypatch.setattr(cli_app, "_store", interrupted)
    result = invoke("profiles", "list")
    assert result.exit_code == 130
    assert "✗ Cancelled." in result.stderr


def test_unexpected_errors_are_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> Store:
        raise RuntimeError("a real bug")

    monkeypatch.setattr(cli_app, "_store", broken)
    with pytest.raises(RuntimeError, match="a real bug"):
        invoke("profiles", "list")
