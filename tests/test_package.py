"""The top-level package: exports, version, t3.inspect(), and import side effects."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

import t3api_utils as t3
import t3api_utils.tui
from t3api_utils.tui import inspector


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Mapping[str, Any]], str]] = []

    def __call__(self, rows: Sequence[Mapping[str, Any]], *, title: str = "rows") -> None:
        self.calls.append((list(rows), title))


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    recorder = Spy()
    monkeypatch.setattr(inspector, "run", recorder)
    return recorder


def test_every_export_exists() -> None:
    for name in t3.__all__:
        assert hasattr(t3, name), name
    assert len(set(t3.__all__)) == len(t3.__all__)


def test_version_comes_from_the_installed_metadata() -> None:
    assert t3.__version__ == metadata.version("t3api-utils")


def test_inspect_opens_the_inspector(spy: Spy) -> None:
    rows = [{"id": 1}, {"id": 2}]
    t3.inspect(rows, title="items")
    t3.inspect(rows)
    assert spy.calls == [(rows, "items"), (rows, "rows")]


def test_inspect_with_no_rows_says_so(spy: Spy, capsys: pytest.CaptureFixture[str]) -> None:
    t3.inspect([])
    assert spy.calls == []
    assert "ℹ No rows to inspect." in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["textual", "t3api_utils.tui.inspector"])
def test_inspect_without_textual_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setitem(sys.modules, missing, None)
    if missing == "textual":
        # Force a fresh import of the inspector, which then can't find Textual.
        monkeypatch.delitem(sys.modules, "t3api_utils.tui.inspector", raising=False)
    monkeypatch.delattr(t3api_utils.tui, "inspector", raising=False)
    with pytest.raises(ImportError, match=re.escape(t3.TUI_HINT)) as caught:
        t3.inspect([{"id": 1}])
    assert isinstance(caught.value.__cause__, ImportError)
    assert "pip install 't3api-utils[tui]'" in str(caught.value)


def test_inspector_is_restored_after_the_missing_textual_test(spy: Spy) -> None:
    # Guards against the test above leaking a broken module into later tests.
    t3.inspect([{"id": 1}])
    assert len(spy.calls) == 1


IMPORT_PROBE = r"""
import json, logging, pathlib, socket, sys

import platformdirs

base = pathlib.Path(sys.argv[1])
platformdirs.user_config_dir = lambda *a, **k: str(base / "config")
platformdirs.user_cache_dir = lambda *a, **k: str(base / "cache")

def no_network(*args, **kwargs):
    raise AssertionError("network used during import")

socket.socket.connect = no_network
socket.create_connection = no_network

root_before = list(logging.getLogger().handlers)
import t3api_utils
import t3api_utils.cli
import t3api_utils.cli.main

pkg = logging.getLogger("t3api_utils")
print(json.dumps({
    "root_handlers": [repr(h) for h in logging.getLogger().handlers if h not in root_before],
    "pkg_handlers": [repr(h) for h in pkg.handlers],
    "pkg_level": pkg.level,
    "pkg_propagate": pkg.propagate,
    "textual_loaded": "textual" in sys.modules,
    "files": sorted(str(p.relative_to(base)) for p in base.rglob("*")),
}))
"""


def test_importing_has_no_side_effects(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    env = dict(os.environ)
    repo = str(Path(t3.__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(p for p in (repo, env.get("PYTHONPATH")) if p)
    completed = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE, str(sandbox)],
        cwd=sandbox,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    report = json.loads(completed.stdout)
    assert report == {
        "root_handlers": [],
        "pkg_handlers": [],
        "pkg_level": 0,
        "pkg_propagate": True,
        "textual_loaded": False,
        "files": [],
    }
