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
from rich.console import Console
from rich.table import Table

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

console = Console()

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
        typer.echo("No licenses found.")
        raise typer.Exit(code=1)

    table = Table(title="Available Licenses")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("License Name", style="magenta")
    table.add_column("License Number", style="green")

    for idx, license in enumerate(licenses, start=1):
        table.add_row(str(idx), license["licenseName"], license["licenseNumber"])

    console.print(table)

    choice = typer.prompt("Select a license", type=int)

    if choice < 1 or choice > len(licenses):
        typer.echo("Invalid selection.")
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
    """Generate a default file path with timestamp."""
    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    filename = f"{collection_name}__{license_number}__{timestamp}.{extension}"
    return filename


def _prompt_for_file_path(*, proposed_path: str, file_type: str) -> Path:
    """Prompt user for file path, allowing them to edit the proposed path."""
    console.print(f"Save to {file_type}")
    console.print(f"Proposed path: {proposed_path}")

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
        console.print(f"[green]Saved {len(data)} records to {csv_path}")

    except Exception as e:
        console.print(f"[red]Error saving CSV: {e}")


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
        console.print(f"[green]Saved {len(data)} records to {json_path}")

    except Exception as e:
        console.print(f"[red]Error saving JSON: {e}")


def _action_create_db(*, state: _HandlerState) -> None:
    """Create a DuckDB connection."""
    try:
        state.db_connection = create_duckdb_connection()
        console.print("[green]Created DuckDB connection")
    except Exception as e:
        console.print(f"[red]Error creating database connection: {e}")


def _action_load_db(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Load collection into database."""
    if not state.db_connection:
        console.print("[red]No database connection available")
        return

    try:
        load_db(con=state.db_connection, data=data)
        console.print(f"[green]Loaded {len(data)} records into database")
    except Exception as e:
        console.print(f"[red]Error loading data into database: {e}")


def _action_export_schema(*, state: _HandlerState) -> None:
    """Export and print database schema."""
    if not state.db_connection:
        console.print("[red]No database connection available")
        return

    try:
        schema = export_duckdb_schema(con=state.db_connection)
        console.print("\n[bold]Database Schema:")
        console.print(schema)
    except Exception as e:
        console.print(f"[red]Error exporting schema: {e}")


def _action_open_csv(*, state: _HandlerState) -> None:
    """Open saved CSV file."""
    if not state.csv_file_path or not state.csv_file_path.exists():
        console.print("[red]No CSV file available to open")
        return

    try:
        open_file(path=state.csv_file_path)
        console.print(f"[green]Opened {state.csv_file_path}")
    except Exception as e:
        console.print(f"[red]Error opening CSV file: {e}")


def _action_open_json(*, state: _HandlerState) -> None:
    """Open saved JSON file."""
    if not state.json_file_path or not state.json_file_path.exists():
        console.print("[red]No JSON file available to open")
        return

    try:
        open_file(path=state.json_file_path)
        console.print(f"[green]Opened {state.json_file_path}")
    except Exception as e:
        console.print(f"[red]Error opening JSON file: {e}")


def _get_menu_options(*, state: _HandlerState) -> List[tuple[str, str, bool]]:
    """Get available menu options based on current state."""
    options = []

    # Always available
    options.append(("Save to CSV", "csv", True))
    options.append(("Save to JSON", "json", True))
    options.append(("Create DuckDB connection", "create_db", state.db_connection is None))

    # Conditionally available
    if state.db_connection:
        options.append(("Load into database", "load_db", True))
        options.append(("Export database schema", "export_schema", True))

    if state.csv_file_path and state.csv_file_path.exists():
        options.append((f"Open CSV file ({state.csv_file_path.name})", "open_csv", True))

    if state.json_file_path and state.json_file_path.exists():
        options.append((f"Open JSON file ({state.json_file_path.name})", "open_json", True))

    options.append(("Exit", "exit", True))

    return [(text, action, available) for text, action, available in options if available]


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
        console.print("[red]Cannot handle empty collection")
        return

    # Initialize state
    state = _HandlerState(
        collection_name=collection_name,
        license_number=license_number or "unknown"
    )

    console.print(f"\nCollection Handler: {collection_name} ({len(data):,} items)")

    # Action mapping
    actions = {
        "csv": lambda: _action_save_csv(data=data, state=state),
        "json": lambda: _action_save_json(data=data, state=state),
        "create_db": lambda: _action_create_db(state=state),
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
            console.print(f"Current state: {' | '.join(state_info)}")

        # Get and display menu options
        options = _get_menu_options(state=state)

        console.print("\nOptions:")
        for i, (text, _, _) in enumerate(options, 1):
            console.print(f"  {i}. {text}")

        # Get user choice
        try:
            choice = typer.prompt(f"\nChoice [1-{len(options)}]", type=int)
            if choice < 1 or choice > len(options):
                console.print("[red]Invalid choice. Please try again.")
                continue

            selected_action = options[choice - 1][1]

            if selected_action == "exit":
                console.print("Exiting collection handler")
                break

            # Execute action
            actions[selected_action]()

        except (typer.Abort, KeyboardInterrupt):
            console.print("\nExiting collection handler")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}")

    # Clean up database connection
    if state.db_connection:
        try:
            state.db_connection.close()
        except Exception:
            pass


from collections import defaultdict


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
