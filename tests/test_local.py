"""local.py: filter_rows, flatten, to_csv, to_json, read_rows."""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from t3api_utils import local
from t3api_utils.local import (
    filter_rows,
    flatten,
    get_path,
    ordered_columns,
    read_rows,
    to_csv,
    to_json,
)

ROWS: list[dict[str, Any]] = [
    {"id": 1, "label": "PKG-A", "item": {"name": "Blue Dream", "category": "Flower"}, "qty": 10},
    {"id": 2, "label": "PKG-B", "item": {"name": "OG Kush", "category": "Flower"}, "qty": 0},
    {"id": 3, "label": "PKG-C", "item": {"name": "Gummies", "category": "Edible"}, "qty": 5},
    {"id": 4, "label": "PKG-D", "item": {"name": "Blue Dream", "category": "Flower"}, "qty": 7},
]


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- get_path


def test_get_path() -> None:
    row = {"a": {"b": {"c": 1}}, "x.y": "literal", "s": "str"}
    assert get_path(row, "a.b.c") == 1
    assert get_path(row, "a.b") == {"c": 1}
    assert get_path(row, "x.y") == "literal"  # a literal dotted key wins
    assert get_path(row, "a.missing") is None
    assert get_path(row, "s.deeper") is None
    assert get_path(row, "nope") is None


# --------------------------------------------------------------------------- filter_rows


def test_filter_by_csv(tmp_path: Path) -> None:
    match = write(tmp_path / "m.csv", "label\nPKG-C\nPKG-A\n")
    result = filter_rows(ROWS, match)
    # Results follow the order of the match file, not of the rows.
    assert [r["id"] for r in result] == [3, 1]
    # Copies, not the original dicts.
    assert result[1] == ROWS[0] and result[1] is not ROWS[0]


def test_filter_by_csv_path_string_with_bom(tmp_path: Path) -> None:
    match = tmp_path / "bom.csv"
    match.write_bytes("﻿label\r\nPKG-B\r\n".encode())
    assert [r["id"] for r in filter_rows(ROWS, str(match))] == [2]


@pytest.mark.parametrize("suffix", [".tsv", ".TAB"])
def test_filter_by_tsv(tmp_path: Path, suffix: str) -> None:
    match = write(tmp_path / f"m{suffix}", "label\tqty\nPKG-D\t7\nPKG-B\t0\n")
    assert [r["id"] for r in filter_rows(ROWS, match)] == [4, 2]


def test_filter_by_list_of_dicts() -> None:
    assert [r["id"] for r in filter_rows(ROWS, [{"id": 4}, {"id": 2}])] == [4, 2]


def test_filter_values_compare_as_stripped_strings(tmp_path: Path) -> None:
    match = write(tmp_path / "m.csv", "id,label\n  3 , PKG-C \n")
    assert [r["id"] for r in filter_rows(ROWS, match)] == [3]


def test_filter_dotted_columns(tmp_path: Path) -> None:
    match = write(tmp_path / "m.csv", "item.name\nGummies\nBlue Dream\n")
    # Several rows share a key: all of them come back, in row order within the key.
    assert [r["id"] for r in filter_rows(ROWS, match)] == [3, 1, 4]


def test_filter_columns_argument_restricts_comparison(tmp_path: Path) -> None:
    match = write(tmp_path / "m.csv", "label,note\nPKG-A,ignored column\n")
    assert [r["id"] for r in filter_rows(ROWS, match, columns=["label"])] == [1]


def test_filter_no_duplicate_rows(tmp_path: Path) -> None:
    match = write(tmp_path / "m.csv", "item.name\nBlue Dream\nBlue Dream\nBlue Dream\n")
    assert [r["id"] for r in filter_rows(ROWS, match)] == [1, 4]


def test_filter_key_value_types() -> None:
    rows = [
        {"id": 1, "flag": True, "tags": ["b", "a"], "meta": {"z": 1, "a": 2}, "none": None},
        {"id": 2, "flag": False, "tags": [], "meta": {}, "none": "x"},
    ]
    assert [r["id"] for r in filter_rows(rows, [{"flag": "true"}])] == [1]
    assert [r["id"] for r in filter_rows(rows, [{"flag": "false"}])] == [2]
    assert [r["id"] for r in filter_rows(rows, [{"tags": '["b", "a"]'}])] == [1]
    assert [r["id"] for r in filter_rows(rows, [{"meta": '{"a": 2, "z": 1}'}])] == [1]
    assert [r["id"] for r in filter_rows(rows, [{"none": ""}])] == [1]
    assert [r["id"] for r in filter_rows(rows, [{"none": None}])] == [1]


def test_filter_missing_column_raises(tmp_path: Path) -> None:
    match = write(tmp_path / "m.csv", "label,colour\nPKG-A,red\n")
    with pytest.raises(ValueError, match=r"Column\(s\) colour aren't in the rows\. Available: id, item, label, qty"):
        filter_rows(ROWS, match)


def test_filter_missing_dotted_column_raises() -> None:
    with pytest.raises(ValueError, match="item.colour"):
        filter_rows(ROWS, [{"item.colour": "red"}])
    with pytest.raises(ValueError, match="label.deeper"):
        filter_rows(ROWS, [{"label.deeper": "x"}])


def test_filter_column_present_in_some_rows_is_fine() -> None:
    rows: list[dict[str, Any]] = [{"id": 1}, {"id": 2, "extra": "yes"}]
    assert filter_rows(rows, [{"extra": "yes"}]) == [{"id": 2, "extra": "yes"}]


def test_filter_on_unmatched_warn(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        result = filter_rows(ROWS, [{"label": "PKG-A"}, {"label": "NOPE"}])
    assert [r["id"] for r in result] == [1]
    assert caplog.records[0].getMessage() == "1 of 2 match line(s) found no row: NOPE"


def test_filter_on_unmatched_error() -> None:
    with pytest.raises(ValueError, match="1 of 2 match line"):
        filter_rows(ROWS, [{"label": "PKG-A"}, {"label": "NOPE"}], on_unmatched="error")


def test_filter_on_unmatched_skip(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="t3api_utils"):
        result = filter_rows(ROWS, [{"label": "NOPE"}, {"label": "PKG-B"}], on_unmatched="skip")
    assert [r["id"] for r in result] == [2]
    assert caplog.records == []


def test_filter_unmatched_message_is_capped() -> None:
    match = [{"label": f"MISSING-{i:02d}", "qty": "1"} for i in range(13)]
    with pytest.raises(ValueError) as info:
        filter_rows(ROWS, match, on_unmatched="error")
    message = str(info.value)
    assert message.startswith("13 of 13 match line(s) found no row: MISSING-00, 1; MISSING-01, 1;")
    assert "MISSING-09" in message and "MISSING-10" not in message
    assert message.endswith("(and 3 more)")


def test_filter_invalid_on_unmatched() -> None:
    with pytest.raises(ValueError, match="on_unmatched"):
        filter_rows(ROWS, [{"id": 1}], on_unmatched="ignore")  # type: ignore[arg-type]


def test_filter_no_columns() -> None:
    with pytest.raises(ValueError, match="No columns"):
        filter_rows(ROWS, [])
    with pytest.raises(ValueError, match="No columns"):
        filter_rows(ROWS, [{}])


def test_filter_empty_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No columns"):
        filter_rows(ROWS, write(tmp_path / "empty.csv", ""))


def test_filter_header_only_file_returns_nothing(tmp_path: Path) -> None:
    assert filter_rows(ROWS, write(tmp_path / "h.csv", "label\n")) == []


def test_filter_empty_match_list_with_columns() -> None:
    assert filter_rows(ROWS, [], columns=["label"]) == []


def test_filter_no_rows_warns_about_every_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert filter_rows([], [{"label": "PKG-A"}]) == []
    assert "1 of 1 match line(s) found no row" in caplog.text


# --------------------------------------------------------------------------- flatten / columns


def test_flatten() -> None:
    row = {
        "id": 1,
        "item": {"name": "Blue Dream", "strain": {"name": "BD", "thc": 0.2}},
        "empty": {},
        "tags": ["a", "ü"],
        "pair": (1, 2),
        "when": [datetime(2026, 1, 2, 3, 4, 5)],
        "none": None,
        "flag": False,
        "zero": 0,
    }
    assert flatten(row) == {
        "id": 1,
        "item.name": "Blue Dream",
        "item.strain.name": "BD",
        "item.strain.thc": 0.2,
        "empty": "",
        "tags": '["a", "ü"]',
        "pair": "[1, 2]",
        "when": '["2026-01-02 03:04:05"]',
        "none": "",
        "flag": False,
        "zero": 0,
    }
    assert flatten({"a": 1}, prefix="p.") == {"p.a": 1}


def test_ordered_columns() -> None:
    rows = [{"zeta": 1, "name": "n", "id": 1}, {"alpha": 2, "licenseNumber": "L", "hostname": "h"}]
    assert ordered_columns(rows) == ["hostname", "licenseNumber", "id", "name", "alpha", "zeta"]
    assert ordered_columns([]) == []


def test_default_path() -> None:
    stamp = r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}"
    path = local.default_path([{"dataModel": "ACTIVE_PACKAGE", "licenseNumber": "LIC-1"}], "csv")
    assert re.fullmatch(rf"ACTIVE_PACKAGE__LIC-1__{stamp}\.csv", str(path))
    assert re.fullmatch(rf"rows__{stamp}\.json", str(local.default_path([], "json")))
    unsafe = local.default_path([{"dataModel": "a/b c", "licenseNumber": "x:y"}], "csv")
    assert re.fullmatch(rf"a_b_c__x_y__{stamp}\.csv", str(unsafe))


# --------------------------------------------------------------------------- to_csv


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_to_csv_writes_bom_dotted_columns_and_json_lists(tmp_path: Path) -> None:
    rows = [
        {"name": "Blue Dream", "id": 1, "item": {"category": "Flower"}, "tags": ["a", "b"], "note": None},
        {"id": 2, "name": "Gummies", "extra": "only here"},
    ]
    target = to_csv(rows, tmp_path / "out.csv")
    assert target == tmp_path / "out.csv"
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    header = raw[3:].split(b"\r\n", 1)[0].decode()
    assert header == "id,name,extra,item.category,note,tags"
    assert read_csv(target) == [
        {"id": "1", "name": "Blue Dream", "extra": "", "item.category": "Flower", "note": "", "tags": '["a", "b"]'},
        {"id": "2", "name": "Gummies", "extra": "only here", "item.category": "", "note": "", "tags": ""},
    ]


def test_to_csv_strip_empty(tmp_path: Path) -> None:
    rows = [{"id": 1, "blank": "", "none": None, "half": ""}, {"id": 2, "blank": "", "half": "x"}]
    target = to_csv(rows, tmp_path / "s.csv", strip_empty=True)
    assert list(read_csv(target)[0]) == ["id", "half"]


def test_to_csv_columns_pick_and_order(tmp_path: Path) -> None:
    target = to_csv(ROWS, tmp_path / "c.csv", columns=["item.name", "id"])
    assert read_csv(target)[0] == {"item.name": "Blue Dream", "id": "1"}


def test_to_csv_default_name_in_current_folder(isolated: Path) -> None:
    target = to_csv([{"dataModel": "ITEM", "licenseNumber": "LIC-9", "id": 1}])
    assert not target.is_absolute()
    assert target.name.startswith("ITEM__LIC-9__") and target.suffix == ".csv"
    assert (isolated / "work" / target).exists()


def test_to_csv_creates_parent_folders(tmp_path: Path) -> None:
    target = to_csv([{"id": 1}], str(tmp_path / "a" / "b" / "x.csv"))
    assert target.exists()


def test_to_csv_empty_rows(tmp_path: Path) -> None:
    target = to_csv([], tmp_path / "e.csv")
    assert target.read_bytes() == b"\xef\xbb\xbf\r\n"


def test_to_csv_round_trip(tmp_path: Path) -> None:
    target = to_csv(ROWS, tmp_path / "rt.csv")
    back = read_rows(target)
    assert [r["label"] for r in back] == ["PKG-A", "PKG-B", "PKG-C", "PKG-D"]
    assert back[0]["item.name"] == "Blue Dream"
    assert back[1]["qty"] == "0"


# --------------------------------------------------------------------------- to_json


def test_to_json_indented(tmp_path: Path) -> None:
    rows = [{"id": 1, "name": "ü", "when": datetime(2026, 1, 2)}]
    target = to_json(rows, tmp_path / "o.json")
    text = target.read_text(encoding="utf-8")
    assert text == '[\n  {\n    "id": 1,\n    "name": "ü",\n    "when": "2026-01-02 00:00:00"\n  }\n]\n'


def test_to_json_lines(tmp_path: Path) -> None:
    target = to_json([{"id": 1}, {"id": 2, "n": "ü"}], tmp_path / "o.jsonl", lines=True)
    assert target.read_text(encoding="utf-8") == '{"id": 1}\n{"id": 2, "n": "ü"}\n'


def test_to_json_mapping(tmp_path: Path) -> None:
    target = to_json({"data": [{"id": 1}], "total": 1}, tmp_path / "m.json")
    assert json.loads(target.read_text(encoding="utf-8")) == {"data": [{"id": 1}], "total": 1}
    lines = to_json({"id": 7}, tmp_path / "m.jsonl", lines=True)
    assert lines.read_text(encoding="utf-8") == '{"id": 7}\n'


def test_to_json_default_names(isolated: Path) -> None:
    plain = to_json([{"dataModel": "ITEM", "id": 1}])
    assert plain.name.startswith("ITEM__") and plain.suffix == ".json"
    jsonl = to_json([{"id": 1}], lines=True)
    assert jsonl.name.startswith("rows__") and jsonl.suffix == ".jsonl"
    mapping = to_json({"dataModel": "WHOAMI", "licenseNumber": "L"})
    assert mapping.name.startswith("WHOAMI__L__")
    assert (isolated / "work" / plain).exists()


# --------------------------------------------------------------------------- read_rows


def test_read_rows_csv_and_tsv(tmp_path: Path) -> None:
    assert read_rows(write(tmp_path / "a.csv", "x,y\n1,2\n")) == [{"x": "1", "y": "2"}]
    assert read_rows(write(tmp_path / "a.tsv", "x\ty\n1\t2\n")) == [{"x": "1", "y": "2"}]
    assert read_rows(str(write(tmp_path / "a.tab", "x\n3\n"))) == [{"x": "3"}]


def test_read_rows_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = write(tmp_path / "a.jsonl", '{"a": 1}\n\n   \n{"a": 2}\n')
    assert read_rows(path) == [{"a": 1}, {"a": 2}]


def test_read_rows_json_list(tmp_path: Path) -> None:
    assert read_rows(write(tmp_path / "a.json", '[{"a": 1}, 2, "s"]')) == [{"a": 1}, {"value": 2}, {"value": "s"}]


def test_read_rows_wrapped_data(tmp_path: Path) -> None:
    path = write(tmp_path / "page.json", '{"page": 1, "data": [{"id": 1}, {"id": 2}]}')
    assert read_rows(path) == [{"id": 1}, {"id": 2}]


def test_read_rows_single_object(tmp_path: Path) -> None:
    assert read_rows(write(tmp_path / "o.json", '{"id": 1, "data": "not a list"}')) == [
        {"id": 1, "data": "not a list"}
    ]
    assert read_rows(write(tmp_path / "w.json", '{"id": 2}')) == [{"id": 2}]


def test_read_rows_scalar(tmp_path: Path) -> None:
    assert read_rows(write(tmp_path / "s.json", "42")) == [{"value": 42}]


def test_read_rows_json_with_bom_and_unknown_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_bytes('﻿[{"a": "ü"}]'.encode())
    assert read_rows(path) == [{"a": "ü"}]


def test_read_rows_round_trip_json(tmp_path: Path) -> None:
    assert read_rows(to_json(ROWS, tmp_path / "r.json")) == ROWS
    assert read_rows(to_json(ROWS, tmp_path / "r.jsonl", lines=True)) == ROWS
