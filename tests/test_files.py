import csv
import json
import tempfile
from datetime import datetime
from typing import Any

import pytest

from t3api_utils.file.utils import (
    collection_to_dicts,
    default_json_serializer,
    flatten_dict,
    generate_output_path,
    prioritized_fieldnames,
    save_dicts_to_csv,
    save_dicts_to_json,
)


class DummySerializableObject:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


def test_flatten_dict():
    d = {"a": {"b": 1}, "c": 2}
    assert flatten_dict(d) == {"a.b": 1, "c": 2}


def test_prioritized_fieldnames():
    data = [{"hostname": "host1", "z": "last"}, {"licensenumber": "xyz"}]
    fields = prioritized_fieldnames(data)
    assert "hostname" in fields
    assert "licensenumber" in fields
    assert fields.index("hostname") < fields.index("z")


def test_collection_to_dicts():
    objs = [DummySerializableObject({"x": 1}), DummySerializableObject({"y": 2})]
    assert collection_to_dicts(objs) == [{"x": 1}, {"y": 2}]  # type: ignore


def test_collection_to_dicts_empty_raises():
    with pytest.raises(ValueError):
        collection_to_dicts([])


def test_default_json_serializer_datetime():
    dt = datetime(2022, 1, 1, 12, 0)
    assert default_json_serializer(dt) == "2022-01-01T12:00:00"


def test_default_json_serializer_invalid_type():
    with pytest.raises(TypeError):
        default_json_serializer(set())


def test_generate_output_path():
    path = generate_output_path("TestModel", "ABC123", "tmp", "json")
    assert path.name.endswith(".json")
    assert "TestModel__ABC123" in path.name


def test_save_dicts_to_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        data = [{"a": 1}, {"b": 2}]
        path = save_dicts_to_json(data, "TestModel", "ABC", output_dir=tmpdir)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data


def test_save_dicts_to_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        data = [{"x": 1}, {"x": 2}]
        path = save_dicts_to_csv(data, "TestModel", "XYZ", output_dir=tmpdir)
        with open(path, newline="", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        assert reader[0]["x"] == "1"
        assert reader[1]["x"] == "2"


def test_save_dicts_to_csv_strip_empty_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        data: list[dict[str, Any]] = [{"x": 1, "empty": None}, {"x": 2, "empty": ""}]
        path = save_dicts_to_csv(
            data, "TestModel", "XYZ", output_dir=tmpdir, strip_empty_columns=True
        )
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames is not None
            assert "x" in reader.fieldnames
            assert "empty" not in reader.fieldnames
