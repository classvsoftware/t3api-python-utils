"""Interactive handler methods for collection management."""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import typer

from t3api_utils.db.utils import create_duckdb_connection, export_duckdb_schema
from t3api_utils.main.utils import load_db, _db_has_data as db_has_data
from t3api_utils.file.utils import (
    default_json_serializer,
    flatten_dict,
    open_file,
    prioritized_fieldnames
)
from t3api_utils.style import (
    console,
    print_error,
    print_labeled_info,
    print_progress,
    print_subheader,
    print_success,
    print_warning
)


@dataclass
class HandlerState:
    """State for interactive collection handler."""
    db_connection: Optional[duckdb.DuckDBPyConnection] = None
    csv_file_path: Optional[Path] = None
    json_file_path: Optional[Path] = None
    collection_name: str = "collection"
    license_number: str = ""


def generate_default_path(*, collection_name: str, license_number: str, extension: str) -> str:
    """Generate a default file path with timestamp in output/ directory."""
    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    filename = f"{collection_name}__{license_number}__{timestamp}.{extension}"
    return f"output/{filename}"


def prompt_for_file_path(*, proposed_path: str, file_type: str) -> Path:
    """Prompt user for file path, allowing them to edit the proposed path."""
    print_subheader(f"Save to {file_type}")
    print_labeled_info("Proposed path", proposed_path)

    user_input = typer.prompt(
        "Enter path (or press Enter to use proposed)",
        default=proposed_path,
        show_default=False
    )

    path = Path(user_input.strip())

    # Create parent directories if they don't exist
    path.parent.mkdir(parents=True, exist_ok=True)

    return path


def action_save_csv(*, data: List[Dict[str, Any]], state: HandlerState) -> None:
    """Save collection to CSV with interactive path selection."""
    default_path = generate_default_path(
        collection_name=state.collection_name,
        license_number=state.license_number,
        extension="csv"
    )

    csv_path = prompt_for_file_path(proposed_path=default_path, file_type="CSV")

    try:
        # Use file/utils functions to flatten and save directly to user's path
        flat_dicts = [flatten_dict(d=d) for d in data]
        fieldnames = prioritized_fieldnames(dicts=flat_dicts)

        with open(csv_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat_dicts)

        state.csv_file_path = csv_path
        print_success(f"Saved {len(data)} records to {csv_path}")

        # Automatically open the file
        open_file(path=csv_path)
        print_success(f"Opened {csv_path}")

    except Exception as e:
        print_error(f"Error saving CSV: {e}")


def action_save_json(*, data: List[Dict[str, Any]], state: HandlerState) -> None:
    """Save collection to JSON with interactive path selection."""
    default_path = generate_default_path(
        collection_name=state.collection_name,
        license_number=state.license_number,
        extension="json"
    )

    json_path = prompt_for_file_path(proposed_path=default_path, file_type="JSON")

    try:
        # Save directly to user's chosen path
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
                default=lambda obj: default_json_serializer(obj=obj)
            )

        state.json_file_path = json_path
        print_success(f"Saved {len(data)} records to {json_path}")

        # Automatically open the file
        open_file(path=json_path)
        print_success(f"Opened {json_path}")

    except Exception as e:
        print_error(f"Error saving JSON: {e}")


def action_load_db(*, data: List[Dict[str, Any]], state: HandlerState) -> None:
    """Load collection into database (auto-creates DB connection if needed)."""
    # Auto-setup: Create database connection if needed
    if not state.db_connection:
        print_progress("Creating database connection...")
        try:
            state.db_connection = create_duckdb_connection()
            print_success("Database connection created")
        except Exception as e:
            print_error(f"Error creating database connection: {e}")
            return

    try:
        load_db(con=state.db_connection, data=data)
        print_success(f"Loaded {len(data)} records into database")
    except Exception as e:
        print_error(f"Error loading data into database: {e}")


def action_export_schema(*, state: HandlerState) -> None:
    """Export and print database schema (auto-creates connection and checks for data)."""
    # Auto-setup: Create database connection if needed
    if not state.db_connection:
        print_progress("Creating database connection...")
        try:
            state.db_connection = create_duckdb_connection()
            print_success("Database connection created")
        except Exception as e:
            print_error(f"Error creating database connection: {e}")
            return

    # Check if database has any data
    if not db_has_data(con=state.db_connection):
        print_warning("Database has no tables. Load data first using 'Load into database' option.")
        return

    try:
        schema = export_duckdb_schema(con=state.db_connection)
        print_subheader("Database Schema")
        console.print(f"[bright_white]{schema}[/bright_white]")
    except Exception as e:
        print_error(f"Error exporting schema: {e}")


def action_inspect_collection(*, data: List[Dict[str, Any]], state: HandlerState) -> None:
    """Launch collection inspector."""
    # Import here to avoid circular imports
    from t3api_utils.main.utils import inspect_collection
    inspect_collection(data=data)


def action_filter_by_csv(*, data: List[Dict[str, Any]], state: HandlerState) -> List[Dict[str, Any]]:
    """Filter collection by CSV matches and return filtered data."""
    try:
        # Import here to avoid circular imports
        from t3api_utils.main.utils import match_collection_from_csv

        filtered_data = match_collection_from_csv(
            data=data,
            on_no_match="warn"  # Default to warn for interactive use
        )

        if filtered_data:
            print_success(f"Collection filtered: {len(filtered_data)} items selected")
            return filtered_data
        else:
            print_warning("No matches found - original collection unchanged")
            return data

    except Exception as e:
        print_error(f"CSV filtering failed: {e}")
        return data


def get_menu_options(*, state: HandlerState) -> List[tuple[str, str]]:
    """Get all menu options (always show all options, auto-setup handles prerequisites)."""
    options = []

    # Core actions - always available
    options.append(("Inspect collection", "inspect"))
    options.append(("Filter by CSV matches", "filter_csv"))
    options.append(("Save to CSV", "csv"))
    options.append(("Save to JSON", "json"))
    options.append(("Load into database", "load_db"))
    options.append(("Export database schema", "export_schema"))

    options.append(("Exit", "exit"))

    return options