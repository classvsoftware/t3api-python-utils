"""t3api_utils.pickers: numbered Rich-table pickers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from t3api_utils import _console, pickers
from t3api_utils.errors import NotInteractive
from t3api_utils.spec.registry import Endpoint

PIES = ["apple pie", "banana split", "cherry pie", "blueberry pie"]


def by_name(item: str) -> list[str]:
    return [item]


@dataclass
class Answers:
    queue: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def ask(
        self, text: str, *, default: str | None = None, password: bool = False, allow_empty: bool = False
    ) -> str:
        self.prompts.append(text)
        if not self.queue:
            raise AssertionError(f"unexpected prompt {text!r}")
        return self.queue.pop(0)


@pytest.fixture(autouse=True)
def wide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    for name in ("FORCE_COLOR", "TTY_COMPATIBLE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> Answers:
    """A terminal is present; ``answers.queue`` holds what the person types."""
    scripted = Answers()
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    monkeypatch.setattr(_console, "ask", scripted.ask)
    return scripted


# --------------------------------------------------------------------------- choose


def test_choose_needs_a_terminal() -> None:
    with pytest.raises(NotInteractive, match=r"^Pies needs a terminal to ask in\.$"):
        pickers.choose("Pies", PIES, ["Pie"], by_name)


def test_choose_with_nothing_to_choose(answers: Answers) -> None:
    with pytest.raises(ValueError, match=r"^Pies: nothing to choose from\.$"):
        pickers.choose("Pies", [], ["Pie"], by_name)
    assert answers.prompts == []


def test_choose_by_number(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["2"]
    assert pickers.choose("Pies", PIES, ["Pie", "Kind"], lambda p: [p, "dessert"]) == "banana split"
    assert answers.prompts == ["Number"]
    err = capsys.readouterr().err
    assert "Pies" in err and "Pie" in err and "Kind" in err and "dessert" in err
    for number, pie in enumerate(PIES, 1):
        assert any(str(number) in line and pie in line for line in err.splitlines())


def test_choose_rejects_numbers_out_of_range(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["0", "5", "4"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name) == "blueberry pie"
    assert capsys.readouterr().err.count("✗ Pick a number from 1 to 4.") == 2
    assert answers.prompts == ["Number"] * 3


def test_choose_without_filtering_needs_a_number(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["cherry", "²", "3"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name) == "cherry pie"
    assert capsys.readouterr().err.count("✗ Type a number.") == 2


def test_choose_filters_by_every_word(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["PIE", "3"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name, filterable=True) == "blueberry pie"
    assert answers.prompts == ["Number, or text to filter"] * 2

    answers.queue = ["pie cherry", "1"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name, filterable=True) == "cherry pie"


def test_choose_filters_start_from_the_full_list(answers: Answers) -> None:
    # A second filter narrows the whole list again, not the previous result.
    answers.queue = ["split", "cherry", "1"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name, filterable=True) == "cherry pie"


def test_choose_no_match_resets_the_list(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["split", "zzz", "4"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name, filterable=True) == "blueberry pie"
    assert "✗ Nothing matches 'zzz'." in capsys.readouterr().err


def test_choose_number_applies_to_the_narrowed_list(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["split", "2", "1"]
    assert pickers.choose("Pies", PIES, ["Pie"], by_name, filterable=True) == "banana split"
    assert "✗ Pick a number from 1 to 1." in capsys.readouterr().err


def test_choose_pages_long_lists(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    items = [f"item-{i:02d}" for i in range(45)]
    answers.queue = ["41", "item-44", "1"]
    assert pickers.choose("Items", items, ["Item"], by_name, filterable=True) == "item-44"
    err = capsys.readouterr().err
    first_table = err.split("Showing 40 of 45")[0]
    assert "item-39" in first_table
    assert "item-40" not in first_table
    assert "ℹ Showing 40 of 45. Type text to narrow the list." in err
    assert "✗ Pick a number from 1 to 40." in err


def test_choose_accepts_a_tuple(answers: Answers) -> None:
    answers.queue = ["1"]
    assert pickers.choose("Pies", tuple(PIES), ["Pie"], by_name) == "apple pie"


# --------------------------------------------------------------------------- pick_license


def test_pick_license_single_needs_no_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    assert pickers.pick_license([{"licenseNumber": "LIC-1", "licenseName": "Only"}]) == "LIC-1"
    assert "ℹ Using the only license available: LIC-1" in capsys.readouterr().err


def test_pick_license_from_a_few(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    licenses = [
        {"licenseNumber": "LIC-1", "licenseName": "North"},
        {"licenseNumber": "LIC-2"},
        {"licenseName": "No number"},
    ]
    answers.queue = ["2"]
    assert pickers.pick_license(licenses) == "LIC-2"
    assert answers.prompts == ["Number"]
    err = capsys.readouterr().err
    assert "Licenses" in err and "North" in err and "No number" in err


def test_pick_license_from_many_can_filter(answers: Answers) -> None:
    licenses = [{"licenseNumber": f"LIC-{i:02d}", "licenseName": f"Store {i}"} for i in range(11)]
    licenses.append({"licenseNumber": "LIC-99", "licenseName": "Warehouse"})
    answers.queue = ["warehouse", "1"]
    assert pickers.pick_license(licenses) == "LIC-99"
    assert answers.prompts == ["Number, or text to filter"] * 2


def test_pick_license_without_terminal() -> None:
    with pytest.raises(NotInteractive, match="Licenses needs a terminal"):
        pickers.pick_license([{"licenseNumber": "A"}, {"licenseNumber": "B"}])


# --------------------------------------------------------------------------- pick_endpoint


def endpoint(id: str | None, path: str, summary: str = "") -> Endpoint:
    return Endpoint(id=id, method="GET", path=path, kind="collection", summary=summary)


ENDPOINTS = [
    endpoint(None, "/v2/saved-reports", "Saved reports"),
    endpoint("METRC_ACTIVE_PACKAGES", "/v2/packages/active", "Active packages"),
    endpoint("METRC_ACTIVE_ITEMS", "/v2/items", "Active items"),
]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("1", "/v2/items"), ("2", "/v2/packages/active"), ("3", "/v2/saved-reports")],
)
def test_pick_endpoint_sorted_by_id_with_unnamed_last(answers: Answers, answer: str, expected: str) -> None:
    answers.queue = [answer]
    assert pickers.pick_endpoint(ENDPOINTS).path == expected


def test_pick_endpoint_filters(answers: Answers, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["packages", "1"]
    assert pickers.pick_endpoint(ENDPOINTS).id == "METRC_ACTIVE_PACKAGES"
    assert answers.prompts == ["Number, or text to filter"] * 2
    assert "GET /v2/packages/active" in capsys.readouterr().err


# --------------------------------------------------------------------------- pick_file


def make_file(path: Path, size: int, mtime: int) -> Path:
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    make_file(root / "a.csv", 10, 1_000_000)
    make_file(root / "b.json", 1234, 2_000_000)
    make_file(root / "c.jsonl", 5, 3_000_000)
    make_file(root / "d.tsv", 7, 1_500_000)
    make_file(root / "notes.txt", 3, 4_000_000)
    (root / "folder.csv").mkdir()
    return root


def test_pick_file_needs_a_terminal(folder: Path) -> None:
    with pytest.raises(NotInteractive, match="Files needs a terminal"):
        pickers.pick_file(folder)


@pytest.mark.parametrize(
    ("answer", "name"),
    [("1", "c.jsonl"), ("2", "b.json"), ("3", "d.tsv"), ("4", "a.csv")],
)
def test_pick_file_newest_first(answers: Answers, folder: Path, answer: str, name: str) -> None:
    answers.queue = [answer]
    assert pickers.pick_file(folder) == folder / name


def test_pick_file_lists_only_matching_files(
    answers: Answers, folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers.queue = ["5", "json", "2"]
    assert pickers.pick_file(str(folder)) == folder / "b.json"
    err = capsys.readouterr().err
    assert "✗ Pick a number from 1 to 4." in err
    assert "1,234 bytes" in err
    assert "notes.txt" not in err
    assert "folder.csv" not in err


def test_pick_file_custom_patterns_and_title(answers: Answers, folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    answers.queue = ["1"]
    assert pickers.pick_file(folder, patterns=("*.txt",), title="Notes") == folder / "notes.txt"
    assert "Notes" in capsys.readouterr().err


def test_pick_file_defaults_to_the_current_folder(answers: Answers) -> None:
    make_file(Path("here.csv"), 1, 1_000_000)
    answers.queue = ["1"]
    assert pickers.pick_file() == Path("here.csv")


def test_pick_file_asks_for_a_path_when_nothing_matches(
    answers: Answers, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    target = make_file(tmp_path / "elsewhere.csv", 1, 1_000_000)
    answers.queue = ["missing.csv", str(empty), str(target)]
    assert pickers.pick_file(empty) == target
    err = capsys.readouterr().err
    assert "No *.csv, *.tsv, *.json, *.jsonl files in" in err
    assert "empty" in err
    assert "✗ missing.csv isn't a file." in err
    assert err.count("isn't a file.") == 2
    assert answers.prompts == ["Path to the file"] * 3


def test_pick_file_expands_the_home_folder(
    answers: Answers, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    make_file(home / "data.csv", 1, 1_000_000)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    empty = tmp_path / "empty"
    empty.mkdir()
    answers.queue = ["~/data.csv"]
    assert pickers.pick_file(empty) == home / "data.csv"


def test_choose_passes_items_through_unchanged(answers: Answers) -> None:
    items: list[dict[str, Any]] = [{"n": 1}, {"n": 2}]
    answers.queue = ["2"]
    assert pickers.choose("Rows", items, ["N"], lambda r: [str(r["n"])]) is items[1]


def test_nothing_to_choose_is_reported_before_the_terminal_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_console, "is_interactive", lambda: False)
    with pytest.raises(ValueError, match="nothing to choose from"):
        pickers.choose("Pies", [], ["Pie"], by_name)
