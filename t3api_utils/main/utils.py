"""Main utilities for T3 API data operations using httpx-based API client."""
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (Any, Callable, Dict, List, Optional, ParamSpec, TypeVar,
                    cast)

import duckdb
import typer
from rich.table import Table

from t3api_utils.style import (
    console,
    print_error,
    print_header,
    print_info,
    print_labeled_info,
    print_menu_item,
    print_progress,
    print_state_info,
    print_subheader,
    print_success,
    print_warning,
)

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse, MetrcObject
from t3api_utils.api.operations import get_data
from t3api_utils.api.parallel import (load_all_data_sync,
                                      parallel_load_collection_enhanced)
from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.auth.utils import (
    create_credentials_authenticated_client_or_error,
    create_credentials_authenticated_client_or_error_async,
    create_jwt_authenticated_client)
from t3api_utils.cli.utils import resolve_auth_inputs_or_error
from t3api_utils.collection.utils import extract_data, parallel_load_collection
from t3api_utils.db.utils import (create_duckdb_connection, create_table_from_data,
                                  export_duckdb_schema, flatten_and_extract)
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.file.utils import (collection_to_dicts, open_file,
                                    save_dicts_to_csv, save_dicts_to_json)
from t3api_utils.interfaces import HasData, P, SerializableObject, T
from t3api_utils.logging import get_logger

logger = get_logger(__name__)


async def get_authenticated_client_or_error_async() -> T3APIClient:
    """
    High-level method to return an authenticated httpx-based T3 API client (async).

    Returns:
        T3APIClient: Authenticated httpx-based client

    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        credentials: T3Credentials = resolve_auth_inputs_or_error()
    except AuthenticationError as e:
        logger.error(f"Authentication input error: {e}")
        raise
    except Exception as e:
        logger.exception("Unexpected error while resolving authentication inputs.")
        raise

    try:
        api_client = await create_credentials_authenticated_client_or_error_async(**credentials)
        logger.info("[bold green]Successfully authenticated with T3 API.[/]")
        return api_client
    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        raise
    except Exception as e:
        logger.exception("Unexpected error while creating authenticated client.")
        raise


def get_authenticated_client_or_error() -> T3APIClient:
    """
    High-level method to return an authenticated httpx-based T3 API client (sync wrapper).

    Returns:
        T3APIClient: Authenticated httpx-based client

    Raises:
        AuthenticationError: If authentication fails
    """
    import asyncio
    return asyncio.run(get_authenticated_client_or_error_async())


def get_jwt_authenticated_client_or_error(*, jwt_token: str) -> T3APIClient:
    """
    High-level method to return a JWT-authenticated httpx-based T3 API client.

    This function provides a simple way to create an authenticated client
    using a pre-existing JWT token, with proper error handling and logging.

    Args:
        jwt_token: Valid JWT access token for the T3 API

    Returns:
        T3APIClient: Authenticated httpx-based client

    Raises:
        ValueError: If jwt_token is empty or None
        AuthenticationError: If authentication fails
    """
    try:
        api_client = create_jwt_authenticated_client(jwt_token)
        logger.info("[bold green]Successfully authenticated with T3 API using JWT token.[/]")
        return api_client
    except ValueError as e:
        logger.error(f"JWT token validation error: {e}")
        raise AuthenticationError(f"Invalid JWT token: {e}") from e
    except Exception as e:
        logger.exception("Unexpected error while creating JWT authenticated client.")
        raise


def pick_license(*, api_client: T3APIClient) -> Dict[str, Any]:
    """
    Interactive license picker using httpx-based T3 API client.

    Args:
        api_client: T3APIClient instance

    Returns:
        Selected license object

    Raises:
        typer.Exit: If no licenses found or invalid selection
    """
    licenses_response = get_data(api_client, "/v2/licenses")
    licenses = licenses_response

    if not licenses:
        print_error("No licenses found.")
        raise typer.Exit(code=1)

    table = Table(title="Available Licenses", border_style="magenta", header_style="bold magenta")
    table.add_column("#", style="magenta", justify="right")
    table.add_column("License Name", style="bright_white")
    table.add_column("License Number", style="cyan")

    for idx, license in enumerate(licenses, start=1):
        table.add_row(str(idx), license["licenseName"], license["licenseNumber"])

    console.print(table)

    choice = typer.prompt("Select a license", type=int)

    if choice < 1 or choice > len(licenses):
        print_error("Invalid selection.")
        raise typer.Exit(code=1)

    selected_license = licenses[choice - 1]
    return cast(Dict[str, Any], selected_license)


def load_collection(
    method: Callable[P, HasData[T]],
    max_workers: int | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> List[T]:
    """
    Loads and flattens a full paginated collection in parallel, preserving type safety.

    Args:
        method: A callable that fetches a single page and returns an object with a `.data: List[T]` attribute.
        max_workers: Optional max number of threads to use.
        *args: Positional arguments for the method.
        **kwargs: Keyword arguments for the method.

    Returns:
        List[T]: A flattened list of all items across all pages.
    """
    all_responses = parallel_load_collection(method, max_workers, *args, **kwargs)
    return extract_data(responses=all_responses)


def save_collection_to_json(
    *,
    objects: List[SerializableObject],
    output_dir: str = "output",
    open_after: bool = False,
    filename_override: Optional[str] = None,
) -> Path:
    """
    Converts and saves a SerializableObject collection to a JSON file.
    Optionally opens the file after saving.
    Returns the path to the saved file.
    """
    if not objects:
        raise ValueError("Cannot serialize an empty list of objects")

    dicts = collection_to_dicts(objects=objects)
    file_path = save_dicts_to_json(
        dicts=dicts,
        model_name=filename_override or objects[0].index,
        license_number=objects[0].license_number,
        output_dir=output_dir,
    )

    if open_after:
        open_file(path=file_path)

    return file_path


def save_collection_to_csv(
    *,
    objects: List[SerializableObject],
    output_dir: str = "output",
    open_after: bool = False,
    filename_override: Optional[str] = None,
    strip_empty_columns: bool = False,
) -> Path:
    """
    Converts and saves a SerializableObject collection to a CSV file.
    Optionally opens the file after saving.
    Returns the path to the saved file.
    """
    if not objects:
        raise ValueError("Cannot serialize an empty list of objects")

    dicts = collection_to_dicts(objects=objects)
    file_path = save_dicts_to_csv(
        dicts=dicts,
        model_name=filename_override or objects[0].index,
        license_number=objects[0].license_number,
        output_dir=output_dir,
        strip_empty_columns=strip_empty_columns,
    )

    if open_after:
        open_file(path=file_path)

    return file_path


@dataclass
class _HandlerState:
    """State for interactive collection handler."""
    db_connection: Optional[duckdb.DuckDBPyConnection] = None
    csv_file_path: Optional[Path] = None
    json_file_path: Optional[Path] = None
    collection_name: str = "collection"
    license_number: str = ""


def _generate_default_path(*, collection_name: str, license_number: str, extension: str) -> str:
    """Generate a default file path with timestamp in output/ directory."""
    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    filename = f"{collection_name}__{license_number}__{timestamp}.{extension}"
    return f"output/{filename}"


def _prompt_for_file_path(*, proposed_path: str, file_type: str) -> Path:
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


def _action_save_csv(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Save collection to CSV with interactive path selection."""
    default_path = _generate_default_path(
        collection_name=state.collection_name,
        license_number=state.license_number,
        extension="csv"
    )

    csv_path = _prompt_for_file_path(proposed_path=default_path, file_type="CSV")

    try:
        # Use file/utils functions to flatten and save directly to user's path
        from t3api_utils.file.utils import flatten_dict, prioritized_fieldnames
        import csv

        flat_dicts = [flatten_dict(d=d) for d in data]
        fieldnames = prioritized_fieldnames(dicts=flat_dicts)

        with open(csv_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat_dicts)

        state.csv_file_path = csv_path
        print_success(f"Saved {len(data)} records to {csv_path}")

    except Exception as e:
        print_error(f"Error saving CSV: {e}")


def _action_save_json(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Save collection to JSON with interactive path selection."""
    default_path = _generate_default_path(
        collection_name=state.collection_name,
        license_number=state.license_number,
        extension="json"
    )

    json_path = _prompt_for_file_path(proposed_path=default_path, file_type="JSON")

    try:
        # Save directly to user's chosen path
        from t3api_utils.file.utils import default_json_serializer
        import json

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

    except Exception as e:
        print_error(f"Error saving JSON: {e}")


def _action_load_db(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
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


def _action_export_schema(*, state: _HandlerState) -> None:
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
    if not _db_has_data(con=state.db_connection):
        print_warning("Database has no tables. Load data first using 'Load into database' option.")
        return

    try:
        schema = export_duckdb_schema(con=state.db_connection)
        print_subheader("Database Schema")
        console.print(f"[bright_white]{schema}[/bright_white]")
    except Exception as e:
        print_error(f"Error exporting schema: {e}")


def _action_open_csv(*, state: _HandlerState) -> None:
    """Open saved CSV file."""
    if not state.csv_file_path or not state.csv_file_path.exists():
        print_error("No CSV file available to open")
        return

    try:
        open_file(path=state.csv_file_path)
        print_success(f"Opened {state.csv_file_path}")
    except Exception as e:
        print_error(f"Error opening CSV file: {e}")


def _action_open_json(*, state: _HandlerState) -> None:
    """Open saved JSON file."""
    if not state.json_file_path or not state.json_file_path.exists():
        print_error("No JSON file available to open")
        return

    try:
        open_file(path=state.json_file_path)
        print_success(f"Opened {state.json_file_path}")
    except Exception as e:
        print_error(f"Error opening JSON file: {e}")


def _action_inspect_collection(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Launch collection inspector."""
    inspect_collection(data=data, collection_name=state.collection_name)


def _get_menu_options(*, state: _HandlerState) -> List[tuple[str, str]]:
    """Get all menu options (always show all options, auto-setup handles prerequisites)."""
    options = []

    # Core actions - always available
    options.append(("Inspect collection", "inspect"))
    options.append(("Save to CSV", "csv"))
    options.append(("Save to JSON", "json"))
    options.append(("Load into database", "load_db"))
    options.append(("Export database schema", "export_schema"))

    # File opening options - show if files exist
    if _file_exists_and_readable(file_path=state.csv_file_path) and state.csv_file_path:
        options.append((f"Open CSV file ({state.csv_file_path.name})", "open_csv"))

    if _file_exists_and_readable(file_path=state.json_file_path) and state.json_file_path:
        options.append((f"Open JSON file ({state.json_file_path.name})", "open_json"))

    options.append(("Exit", "exit"))

    return options


def interactive_collection_handler(
    *,
    data: List[Dict[str, Any]],
    collection_name: str = "collection",
    license_number: str = ""
) -> None:
    """
    Interactive handler for working with loaded collections.

    Provides a menu-driven interface for saving to files, loading into database,
    exporting schemas, and opening files. State is preserved across operations.

    Args:
        data: List of dictionaries to work with
        collection_name: Name for the collection (used in filenames)
        license_number: License number for the data (used in filenames)
    """
    if not data:
        print_error("Cannot handle empty collection")
        return

    # Initialize state
    state = _HandlerState(
        collection_name=collection_name,
        license_number=license_number or "unknown"
    )

    print_header("Collection Handler")
    print_labeled_info("Dataset", f"{collection_name} ({len(data):,} items)")

    # Action mapping
    actions = {
        "inspect": lambda: _action_inspect_collection(data=data, state=state),
        "csv": lambda: _action_save_csv(data=data, state=state),
        "json": lambda: _action_save_json(data=data, state=state),
        "load_db": lambda: _action_load_db(data=data, state=state),
        "export_schema": lambda: _action_export_schema(state=state),
        "open_csv": lambda: _action_open_csv(state=state),
        "open_json": lambda: _action_open_json(state=state),
        "exit": lambda: None
    }

    while True:
        # Show current state
        state_info = []
        if state.db_connection:
            state_info.append("DB connected")
        if state.csv_file_path:
            state_info.append("CSV saved")
        if state.json_file_path:
            state_info.append("JSON saved")

        if state_info:
            print_state_info(state_info)

        # Get and display menu options
        options = _get_menu_options(state=state)

        console.print("\n[magenta]Options:[/magenta]")
        for i, (text, _) in enumerate(options, 1):
            print_menu_item(i, text)

        # Get user choice
        try:
            choice = typer.prompt(f"\nChoice [1-{len(options)}]", type=int)
            if choice < 1 or choice > len(options):
                print_error("Invalid choice. Please try again.")
                continue

            selected_action = options[choice - 1][1]

            if selected_action == "exit":
                print_info("Exiting collection handler")
                break

            # Execute action
            actions[selected_action]()

        except (typer.Abort, KeyboardInterrupt):
            print_info("Exiting collection handler")
            break
        except Exception as e:
            print_error(f"Error: {e}")

    # Clean up database connection
    if state.db_connection:
        try:
            state.db_connection.close()
        except Exception:
            pass


from collections import defaultdict


def _db_has_data(*, con: duckdb.DuckDBPyConnection) -> bool:
    """Check if the database connection has any tables with data."""
    if not con:
        return False

    try:
        # Get list of tables in main schema
        tables = con.execute(
            """
            SELECT table_name
            FROM duckdb_tables()
            WHERE schema_name = 'main'
            """
        ).fetchall()
        return len(tables) > 0
    except Exception:
        return False


def _file_exists_and_readable(*, file_path: Path | None) -> bool:
    """Check if a file path exists and is readable."""
    return file_path is not None and file_path.exists() and file_path.is_file()


def load_db(*, con: duckdb.DuckDBPyConnection, data: List[Dict[str, Any]]) -> None:
    """
    Loads a list of nested dictionaries into DuckDB, creating separate tables
    for each distinct data_model found within nested objects or arrays.

    This function:
    - Flattens top-level records
    - Extracts nested dicts and lists into separate tables
    - Deduplicates extracted entries by their ID
    - Automatically names tables based on the `data_model` key

    Args:
        con: An active DuckDB connection.
        data: A list of structured dictionaries representing input records.

    Raises:
        ValueError: If table creation fails due to missing or malformed data.
    """
    # Storage for extracted nested tables, keyed by table name then ID
    extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)

    # Flatten top-level data and extract nested tables
    flat_data = flatten_and_extract(data=data, extracted_tables=extracted_tables)

    # Create main/root table from the flattened top-level data
    create_table_from_data(con=con, data_dict=flat_data)

    # Create one table per nested data_model
    for _, data_dict in extracted_tables.items():
        create_table_from_data(con=con, data_dict=data_dict)


def inspect_collection(
    *,
    data: List[Dict[str, Any]],
    collection_name: str = "collection"
) -> None:
    """
    Interactive inspector for exploring collection objects using Textual TUI.

    Features:
    - Scrollable JSON display with syntax highlighting
    - Mouse and keyboard navigation support
    - Interactive buttons with visual feedback
    - Search functionality with live filtering
    - Professional terminal user interface
    - Responsive layout that adapts to terminal size

    Args:
        data: List of dictionaries to inspect
        collection_name: Name for the collection (used in display)
    """
    if not data:
        print_error("Cannot inspect empty collection")
        return

    # Import here to avoid circular import
    from t3api_utils.inspector import inspect_collection as textual_inspect

    textual_inspect(data=data, collection_name=collection_name)
