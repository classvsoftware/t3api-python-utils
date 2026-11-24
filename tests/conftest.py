"""Shared fixtures.

Every test runs with:

* config and cache folders in a temp dir (never the real user folders),
* no T3_* environment variables,
* an in-memory keyring,
* the current directory set to a temp dir,
* no terminal (``_console.is_interactive()`` is False) unless a test patches it,
* ``time.sleep`` replaced with a recorder, so retries don't wait.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import keyring
import keyring.errors
import pytest
from keyring.backend import KeyringBackend

from t3api_utils import _console, _paths
from t3api_utils.auth.credentials import SecretKeyAuth
from t3api_utils.client import T3Client


class MemoryKeyring(KeyringBackend):
    """A keyring that lives in a dict."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self.passwords[(service, username)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError("not found") from None


@pytest.fixture(autouse=True)
def memory_keyring() -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config"
    cache = tmp_path / "cache"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(_paths, "config_dir", lambda: config)
    monkeypatch.setattr(_paths, "cache_dir", lambda: cache)
    for name in list(os.environ):
        if name.startswith("T3_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(work)
    monkeypatch.setattr(_console, "is_interactive", lambda: False)
    return tmp_path


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Every time.sleep() call made during the test, without waiting."""
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: recorded.append(seconds))
    return recorded


Handler = Callable[[httpx2.Request], httpx2.Response]


@dataclass
class Route:
    method: str
    pattern: re.Pattern[str]
    handler: Handler


@dataclass
class Router:
    """A fake T3 API for ``httpx2.MockTransport``.

    ``router.add("GET", "/v2/licenses", json=[...])`` answers one route.
    Paths may contain ``{name}`` placeholders. Unmatched requests get a 404.
    Every request is recorded in ``router.calls``.
    """

    routes: list[Route] = field(default_factory=list)
    calls: list[httpx2.Request] = field(default_factory=list)

    def add(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        handler: Handler | None = None,
    ) -> None:
        pattern = re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")
        if handler is None:

            def handler(request: httpx2.Request) -> httpx2.Response:
                if content is not None:
                    return httpx2.Response(status, content=content, headers=headers)
                return httpx2.Response(status, json=json, headers=headers)

        # Later routes win, so a test can override a default.
        self.routes.insert(0, Route(method.upper(), pattern, handler))

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append(request)
        for route in self.routes:
            if route.method == request.method and route.pattern.match(request.url.path):
                return route.handler(request)
        return httpx2.Response(404, json={"detail": f"no route for {request.method} {request.url.path}"})

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def requests(self, method: str | None = None, path: str | None = None) -> list[httpx2.Request]:
        return [
            r
            for r in self.calls
            if (method is None or r.method == method.upper()) and (path is None or r.url.path == path)
        ]


def paginated(rows: list[dict[str, Any]], page_size: int = 2) -> Handler:
    """A handler that serves ``rows`` as a T3 paginated collection."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        page = int(request.url.params.get("page", "1"))
        size = int(request.url.params.get("pageSize", str(page_size)))
        size = min(size, page_size)
        total_pages = max(1, -(-len(rows) // size))
        chunk = rows[(page - 1) * size : page * size]
        return httpx2.Response(
            200,
            json={"page": page, "totalPages": total_pages, "pageSize": size, "total": len(rows), "data": chunk},
        )

    return handler


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def client(router: Router) -> Iterator[T3Client]:
    """A T3Client with a secret key, the bundled spec, no rate limit, and the fake API."""
    c = T3Client(
        auth=SecretKeyAuth("test-secret-key"),
        transport=router.transport,
        spec="bundled",
        rate_limit=None,
    )
    yield c
    c.close()
