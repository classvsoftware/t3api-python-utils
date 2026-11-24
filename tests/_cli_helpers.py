"""Fixtures and helpers shared by the ``test_cli*.py`` files.

* ``cli_env`` (autouse when imported): wide, uncolored Rich output, and the
  ``t3api_utils`` logger restored after each test (the CLI's root callback adds
  a RichHandler and turns off propagation).
* ``api``: every httpx2 client the CLI builds talks to the ``router`` fake API,
  and the bundled spec is used.
* ``prompts``: scripted answers for ``_console.ask`` / ``_console.confirm``
  with a terminal present.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest
from typer.testing import CliRunner, Result

from t3api_utils import _console, _http
from t3api_utils import client as client_module
from t3api_utils.auth.credentials import CredentialKind
from t3api_utils.auth.store import Profile, Store
from tests.conftest import Router

# The CLI module. cli/__init__.py re-exports its Typer object as ``app``.
cli_app = importlib.import_module("t3api_utils.cli.main")

TINY_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "tiny"},
    "paths": {
        "/v2/widgets": {
            "get": {
                "x-t3-endpoint-id": "WIDGETS",
                "summary": "List widgets",
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}

runner = CliRunner()


def invoke(*args: str) -> Result:
    """Run ``t3api ARGS``; unexpected exceptions propagate to the test."""
    return runner.invoke(cli_app.app, list(args), catch_exceptions=False)


@pytest.fixture(autouse=True)
def cli_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    logger = logging.getLogger("t3api_utils")
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    monkeypatch.setenv("COLUMNS", "200")
    for name in ("FORCE_COLOR", "TTY_COMPATIBLE"):
        monkeypatch.delenv(name, raising=False)
    yield
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, router: Router) -> Router:
    """Route every client the CLI builds (directly or via T3Client) to ``router``."""
    real = _http.build_client

    def offline(**kwargs: Any) -> httpx2.Client:
        kwargs["transport"] = kwargs.get("transport") or router.transport
        kwargs["rate_limit"] = None
        return real(**kwargs)

    monkeypatch.setattr(cli_app, "build_client", offline)
    monkeypatch.setattr(client_module, "build_client", offline)
    monkeypatch.setenv("T3_SPEC", "bundled")
    return router


@dataclass
class Prompts:
    """Scripted answers, keyed by the exact prompt text."""

    answers: dict[str, list[str]] = field(default_factory=dict)
    confirms: dict[str, list[bool]] = field(default_factory=dict)
    asked: list[dict[str, Any]] = field(default_factory=list)
    confirmed: list[dict[str, Any]] = field(default_factory=list)

    def answer(self, text: str, *values: str) -> None:
        self.answers.setdefault(text, []).extend(values)

    def confirm(self, text: str, *values: bool) -> None:
        self.confirms.setdefault(text, []).extend(values)

    def ask(
        self, text: str, *, default: str | None = None, password: bool = False, allow_empty: bool = False
    ) -> str:
        self.asked.append({"text": text, "default": default, "password": password})
        queue = self.answers.get(text)
        if not queue:
            raise AssertionError(f"unexpected prompt {text!r}")
        return queue.pop(0)

    def yes_no(self, text: str, *, default: bool = True) -> bool:
        self.confirmed.append({"text": text, "default": default})
        queue = self.confirms.get(text)
        if not queue:
            raise AssertionError(f"unexpected confirmation {text!r}")
        return queue.pop(0)

    def texts(self) -> list[str]:
        return [a["text"] for a in self.asked]


@pytest.fixture
def prompts(monkeypatch: pytest.MonkeyPatch) -> Prompts:
    """A terminal is present and prompts get scripted answers."""
    scripted = Prompts()
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    monkeypatch.setattr(_console, "ask", scripted.ask)
    monkeypatch.setattr(_console, "confirm", scripted.yes_no)
    return scripted


def save_profile(
    name: str = "default",
    *,
    credential: CredentialKind | None = "secret_key",
    secret: str | None = "sk-default-0001",
    license: str | None = None,
    api_host: str = _http.DEFAULT_HOST,
    metrc_hostname: str | None = None,
    username: str | None = None,
    make_default: bool | None = None,
) -> Profile:
    """Save a profile (and its secret) the way `t3api login` would."""
    store = Store()
    profile = Profile(
        name=name,
        api_host=api_host,
        metrc_hostname=metrc_hostname,
        username=username,
        license=license,
        credential=credential,
    )
    if credential is not None and secret is not None:
        store.set_secret(name, credential, secret)
    store.save_profile(profile, make_default=make_default)
    return profile
