import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from t3api_utils.file.consts import PRIORITY_FIELDS
from t3api_utils.logging import get_logger

logger = get_logger(__name__)


def flatten_dict(
    *, d: Dict[str, Any], parent_key: str = "", sep: str = "."
) -> Dict[str, Any]:
    """
    Recursively flattens a nested dictionary using dot notation.

    Example:
        {"a": {"b": 1}} → {"a.b": 1}
    """
    result: Dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            result.update(flatten_dict(d=v, parent_key=new_key, sep=sep))
        else:
            result[new_key] = v
    return result


def prioritized_fieldnames(*, dicts: List[Dict[str, Any]]) -> List[str]:
    """
    Orders CSV fieldnames by priority list, then appends any additional keys sorted alphabetically.
    """
    all_keys = {key for row in dicts for key in row.keys()}
    prioritized = [key for key in PRIORITY_FIELDS if key in all_keys]
    remaining = sorted(all_keys - set(prioritized))
    return prioritized + remaining




def default_json_serializer(*, obj: object) -> str:
    """
    Fallback serializer for non-JSON-native types.
    Currently handles datetime objects by converting them to ISO format.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def generate_output_path(
    *, model_name: str, license_number: str, output_dir: str, extension: str
) -> Path:
    """
    Constructs the output file path with consistent naming:
        <model_name>__<license_number>__<timestamp>.<ext>
    """
    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    filename = f"{model_name}__{license_number}__{timestamp}.{extension}"
    filepath = Path(output_dir) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    return filepath


def save_dicts_to_json(
    *,
    dicts: List[Dict[str, Any]],
    model_name: str,
    license_number: str,
    output_dir: str = "output",
) -> Path:
    """
    Saves a list of dicts to a JSON file. Returns the saved file path.
    """
    if not dicts:
        raise ValueError("Input list is empty")

    filepath = generate_output_path(model_name=model_name, license_number=license_number, output_dir=output_dir, extension="json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            dicts, f, ensure_ascii=False, indent=2, default=lambda obj: default_json_serializer(obj=obj)
        )

    logger.info(f"Wrote {len(dicts)} {model_name} objects to {filepath}")
    return filepath


def save_dicts_to_csv(
    *,
    dicts: List[Dict[str, Any]],
    model_name: str,
    license_number: str,
    output_dir: str = "output",
    strip_empty_columns: bool = False,
) -> Path:
    """
    Saves a list of (possibly nested) dictionaries to a CSV file after flattening.
    Returns the saved file path.

    Args:
        dicts: List of input dictionaries.
        model_name: Logical model name (used in filename).
        license_number: License identifier (used in filename).
        output_dir: Where to save the file.
        strip_empty_columns: If True, completely empty columns will be removed.
    """
    if not dicts:
        raise ValueError("Input list is empty")

    flat_dicts = [flatten_dict(d=d) for d in dicts]

    if strip_empty_columns:
        # Determine which fields are completely empty
        all_keys = {key for d in flat_dicts for key in d}
        non_empty_keys = {
            key
            for key in all_keys
            if any(d.get(key) not in (None, "", []) for d in flat_dicts)
        }
        flat_dicts = [
            {k: v for k, v in d.items() if k in non_empty_keys} for d in flat_dicts
        ]

    fieldnames = prioritized_fieldnames(dicts=flat_dicts)
    filepath = generate_output_path(model_name=model_name, license_number=license_number, output_dir=output_dir, extension="csv")

    with open(filepath, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_dicts)

    logger.info(f"Wrote {len(flat_dicts)} {model_name} objects to {filepath}")
    return filepath


def open_file(*, path: Path) -> None:
    """
    Opens a file using the default application for the OS.
    """
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":
            os.startfile(path)
        elif os.name == "posix":
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        logger.error(f"Failed to open file: {e}")
