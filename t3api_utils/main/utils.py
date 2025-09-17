"""Main utilities for T3 API data operations using httpx-based API client."""
import os
import subprocess
import sys
from pathlib import Path
from typing import (Any, Callable, Dict, List, Optional, ParamSpec, TypeVar,
                    cast)

import typer
from rich.console import Console
from rich.table import Table

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse, MetrcObject
from t3api_utils.api.parallel import (load_all_data_sync,
                                      parallel_load_collection_enhanced)
from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.auth.utils import \
    create_credentials_authenticated_client_or_error
from t3api_utils.cli.utils import resolve_auth_inputs_or_error
from t3api_utils.collection.utils import extract_data, parallel_load_collection
from t3api_utils.db.utils import create_table_from_data, flatten_and_extract
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.file.utils import (collection_to_dicts, open_file,
                                    save_dicts_to_csv, save_dicts_to_json)
from t3api_utils.interfaces import HasData, P, SerializableObject, T
from t3api_utils.logging import get_logger

console = Console()

logger = get_logger(__name__)


def get_authenticated_client_or_error() -> T3APIClient:
    """
    High-level method to return an authenticated httpx-based T3 API client.

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
        api_client = create_credentials_authenticated_client_or_error(**credentials)
        logger.info("[bold green]Successfully authenticated with T3 API.[/]")
        return api_client
    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        raise
    except Exception as e:
        logger.exception("Unexpected error while creating authenticated client.")
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
    licenses_response = api_client.get_licenses()
    
    print(licenses_response)
    
    licenses = licenses_response["data"]

    if not licenses:
        typer.echo("No licenses found.")
        raise typer.Exit(code=1)

    table = Table(title="Available Licenses")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("License Name", style="magenta")
    table.add_column("License Number", style="green")

    for idx, license in enumerate(licenses, start=1):
        table.add_row(str(idx), license["legalName"], license["licenseNumber"])

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
    return extract_data(all_responses)


def save_collection_to_json(
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

    dicts = collection_to_dicts(objects)
    file_path = save_dicts_to_json(
        dicts,
        model_name=filename_override or objects[0].index,
        license_number=objects[0].license_number,
        output_dir=output_dir,
    )

    if open_after:
        open_file(file_path)

    return file_path


def save_collection_to_csv(
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

    dicts = collection_to_dicts(objects)
    file_path = save_dicts_to_csv(
        dicts,
        model_name=filename_override or objects[0].index,
        license_number=objects[0].license_number,
        output_dir=output_dir,
        strip_empty_columns=strip_empty_columns,
    )

    if open_after:
        open_file(file_path)

    return file_path


from collections import defaultdict
from typing import Any, Dict, List

import duckdb


def load_db(con: duckdb.DuckDBPyConnection, data: List[Dict[str, Any]]) -> None:
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
    flat_data = flatten_and_extract(data, extracted_tables)

    # Create main/root table from the flattened top-level data
    create_table_from_data(con, flat_data)

    # Create one table per nested data_model
    for table_name, data_dict in extracted_tables.items():
        create_table_from_data(con, data_dict)
