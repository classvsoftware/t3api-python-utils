"""Main utilities for T3 API data operations using httpx-based API client."""

import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Union, cast

import duckdb
import typer
from rich.table import Table

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.interfaces import LicenseData, MetrcObject
from t3api_utils.api.operations import send_api_request
from t3api_utils.api.parallel import parallel_load_collection_enhanced
from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.auth.utils import (
    create_api_key_authenticated_client_or_error,
    create_credentials_authenticated_client_or_error_async,
    create_jwt_authenticated_client,
)
from t3api_utils.cli.utils import config_manager, resolve_auth_inputs_or_error
from t3api_utils.collection.utils import extract_data, parallel_load_collection
from t3api_utils.db.utils import (
    create_duckdb_connection,
    create_table_from_data,
    export_duckdb_schema,
    flatten_and_extract,
)
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.file.utils import (
    open_file,
    save_dicts_to_csv,
    save_dicts_to_json,
)
from t3api_utils.api.interfaces import MetrcCollectionResponse, MetrcObject
from t3api_utils.interfaces import P
from t3api_utils.logging import get_logger
from t3api_utils.style import (
    console,
    print_error,
    print_header,
    print_info,
    print_labeled_info,
    print_progress,
    print_state_info,
    print_subheader,
    print_success,
    print_warning,
)

logger = get_logger(__name__)

# Auto-initialize configuration on module import
config_manager.ensure_config_exists()


def _pick_authentication_method() -> str:
    """
    Interactive picker for selecting authentication method.

    Returns:
        Selected authentication method: 'credentials', 'jwt', or 'api_key'

    Raises:
        typer.Exit: If user provides invalid selection
    """
    print_subheader("Authentication Method")

    # Define authentication options
    auth_options = [
        ("credentials", "Credentials", "Username/password authentication"),
        ("jwt", "JWT Token", "Pre-existing JWT token (with validation)"),
        ("api_key", "API Key", "API key + state code authentication"),
    ]

    # Create table following CLI picker standards
    table = Table(
        title="Available Authentication Methods",
        border_style="magenta",
        header_style="bold magenta",
    )
    table.add_column("#", style="magenta", justify="right")
    table.add_column("Method", style="bright_white")
    table.add_column("Description", style="cyan")

    for idx, (_, method, description) in enumerate(auth_options, start=1):
        table.add_row(str(idx), method, description)

    console.print(table)

    # Get user choice
    while True:
        try:
            choice = typer.prompt("Select authentication method (number)", type=int)
            if 1 <= choice <= len(auth_options):
                selected_method: str = auth_options[choice - 1][0]
                return selected_method
            else:
                print_error(f"Invalid selection. Please choose 1-{len(auth_options)}.")
        except (ValueError, typer.Abort, KeyboardInterrupt):
            print_error("Invalid input or operation cancelled.")
            raise typer.Exit(code=1)


async def _authenticate_with_credentials_async() -> T3APIClient:
    """Helper function for credential-based authentication (async)."""
    try:
        credentials: T3Credentials = resolve_auth_inputs_or_error()
    except AuthenticationError as e:
        logger.error(f"Authentication input error: {e}")
        raise
    except Exception as e:
        logger.exception("Unexpected error while resolving authentication inputs.")
        raise

    try:
        api_client = await create_credentials_authenticated_client_or_error_async(
            **credentials
        )
        logger.info(
            "[bold green]Successfully authenticated with T3 API using credentials.[/]"
        )
        return api_client
    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        raise
    except Exception as e:
        logger.exception("Unexpected error while creating authenticated client.")
        raise


def _authenticate_with_credentials() -> T3APIClient:
    """Helper function for credential-based authentication (sync wrapper)."""
    import asyncio

    return asyncio.run(_authenticate_with_credentials_async())


def _authenticate_with_jwt() -> T3APIClient:
    """Helper function for JWT token authentication."""
    print_subheader("JWT Token Authentication")

    # Get JWT token from user
    jwt_token = typer.prompt("Enter JWT token", hide_input=True)

    # Always validate JWT token using /whoami endpoint
    return get_jwt_authenticated_client_or_error_with_validation(jwt_token=jwt_token)


def _authenticate_with_api_key() -> T3APIClient:
    """Helper function for API key authentication."""
    print_subheader("API Key Authentication")

    # Get API key and state code from user
    api_key = typer.prompt("Enter API key", hide_input=True)
    state_code = typer.prompt("Enter state code (e.g., CA, MO, CO, MI)").upper().strip()

    # Validate state code format (basic validation)
    if not state_code or len(state_code) != 2 or not state_code.isalpha():
        print_error(
            "Invalid state code. Please enter a 2-letter state code like CA, MO, CO, MI."
        )
        raise AuthenticationError(f"Invalid state code: {state_code}")

    return get_api_key_authenticated_client_or_error(
        api_key=api_key, state_code=state_code
    )


async def get_authenticated_client_or_error_async() -> T3APIClient:
    """
    High-level method to return an authenticated httpx-based T3 API client (async).

    Displays an interactive picker for authentication method selection and routes to
    the appropriate authentication method based on user choice.

    Returns:
        T3APIClient: Authenticated httpx-based client

    Raises:
        AuthenticationError: If authentication fails
        typer.Exit: If user cancels or provides invalid input
    """
    auth_method = _pick_authentication_method()

    if auth_method == "credentials":
        return await _authenticate_with_credentials_async()
    elif auth_method == "jwt":
        # JWT auth is sync only, so we need to handle it specially
        return _authenticate_with_jwt()
    elif auth_method == "api_key":
        return _authenticate_with_api_key()
    else:
        raise AuthenticationError(f"Unknown authentication method: {auth_method}")


def get_authenticated_client_or_error(
    *, auth_method: Optional[str] = None
) -> T3APIClient:
    """
    High-level method to return an authenticated httpx-based T3 API client (sync wrapper).

    Displays an interactive picker for authentication method selection and routes to
    the appropriate authentication method based on user choice.

    Returns:
        T3APIClient: Authenticated httpx-based client

    Raises:
        AuthenticationError: If authentication fails
        typer.Exit: If user cancels or provides invalid input
    """
    if auth_method is None:
        auth_method = _pick_authentication_method()

    if auth_method == "credentials":
        return _authenticate_with_credentials()
    elif auth_method == "jwt":
        return _authenticate_with_jwt()
    elif auth_method == "api_key":
        return _authenticate_with_api_key()
    else:
        raise AuthenticationError(f"Unknown authentication method: {auth_method}")


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
        api_client = create_jwt_authenticated_client(jwt_token=jwt_token)
        logger.info(
            "[bold green]Successfully authenticated with T3 API using JWT token.[/]"
        )
        return api_client
    except ValueError as e:
        logger.error(f"JWT token validation error: {e}")
        raise AuthenticationError(f"Invalid JWT token: {e}") from e
    except Exception as e:
        logger.exception("Unexpected error while creating JWT authenticated client.")
        raise


def get_jwt_authenticated_client_or_error_with_validation(
    *, jwt_token: str
) -> T3APIClient:
    """
    High-level method to return a JWT-authenticated httpx-based T3 API client with validation.

    This function creates an authenticated client using a pre-existing JWT token and
    validates it by making a test call to the /v2/auth/whoami endpoint to ensure the
    token is valid and not expired.

    Args:
        jwt_token: Valid JWT access token for the T3 API

    Returns:
        T3APIClient: Authenticated httpx-based client that has been validated

    Raises:
        ValueError: If jwt_token is empty or None
        AuthenticationError: If JWT token is invalid, expired, or authentication fails
    """
    try:
        # Create the JWT authenticated client
        api_client = create_jwt_authenticated_client(jwt_token=jwt_token)

        # Validate the JWT token by calling /whoami endpoint
        try:
            whoami_response = send_api_request(api_client, "/v2/auth/whoami")
            logger.info(
                "[bold green]Successfully authenticated and validated JWT token with T3 API.[/]"
            )
            logger.info(
                f"Authenticated as: {whoami_response.get('username', 'Unknown user')}"
            )
            return api_client

        except Exception as validation_error:
            # Close the client on validation failure
            import asyncio

            asyncio.run(api_client.close())

            # Determine the type of validation error
            error_msg = str(validation_error).lower()
            if "401" in error_msg or "unauthorized" in error_msg:
                raise AuthenticationError(
                    "JWT token is invalid or expired"
                ) from validation_error
            elif "403" in error_msg or "forbidden" in error_msg:
                raise AuthenticationError(
                    "JWT token does not have sufficient permissions"
                ) from validation_error
            else:
                raise AuthenticationError(
                    f"JWT token validation failed: {validation_error}"
                ) from validation_error

    except ValueError as e:
        logger.error(f"JWT token validation error: {e}")
        raise AuthenticationError(f"Invalid JWT token: {e}") from e
    except AuthenticationError:
        # Re-raise authentication errors as-is
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error while creating and validating JWT authenticated client."
        )
        raise AuthenticationError(f"Unexpected authentication error: {str(e)}") from e


def get_api_key_authenticated_client_or_error(
    *, api_key: str, state_code: str
) -> T3APIClient:
    """
    High-level method to return an API key-authenticated httpx-based T3 API client.

    This function provides API key authentication using the /v2/auth/apikey endpoint
    with proper error handling and logging.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")

    Returns:
        T3APIClient: Authenticated httpx-based client

    Raises:
        ValueError: If api_key or state_code is empty or None
        AuthenticationError: If authentication fails
    """
    try:
        api_client = create_api_key_authenticated_client_or_error(
            api_key=api_key, state_code=state_code
        )
        logger.info(
            "[bold green]Successfully authenticated with T3 API using API key.[/]"
        )
        return api_client
    except ValueError as e:
        logger.error(f"API key validation error: {e}")
        raise AuthenticationError(f"Invalid API key or state code: {e}") from e
    except AuthenticationError:
        # Re-raise authentication errors as-is
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error while creating API key authenticated client."
        )
        raise AuthenticationError(f"Unexpected authentication error: {str(e)}") from e


def pick_license(*, api_client: T3APIClient) -> LicenseData:
    """
    Interactive license picker using httpx-based T3 API client.

    Args:
        api_client: T3APIClient instance

    Returns:
        Selected license object

    Raises:
        typer.Exit: If no licenses found or invalid selection
    """
    licenses_response: List[LicenseData] = send_api_request(api_client, "/v2/licenses")

    if not licenses_response:
        print_error("No licenses found.")
        raise typer.Exit(code=1)

    table = Table(
        title="Available Licenses", border_style="magenta", header_style="bold magenta"
    )
    table.add_column("#", style="magenta", justify="right")
    table.add_column("License Name", style="bright_white")
    table.add_column("License Number", style="cyan")

    for idx, license in enumerate(licenses_response, start=1):
        table.add_row(str(idx), license["licenseName"], license["licenseNumber"])

    console.print(table)

    choice = typer.prompt("Select a license", type=int)

    if choice < 1 or choice > len(licenses_response):
        print_error("Invalid selection.")
        raise typer.Exit(code=1)

    selected_license = licenses_response[choice - 1]
    return cast(LicenseData, selected_license)


def load_collection(
    method: Callable[P, MetrcCollectionResponse],
    max_workers: int | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> List[MetrcObject]:
    """
    Loads and flattens a full paginated collection in parallel, preserving type safety.

    Args:
        method: A callable that fetches a single page and returns a MetrcCollectionResponse.
        max_workers: Optional max number of threads to use.
        *args: Positional arguments for the method.
        **kwargs: Keyword arguments for the method.

    Returns:
        List[MetrcObject]: A flattened list of all items across all pages.
    """
    all_responses = parallel_load_collection(method, max_workers, *args, **kwargs)
    return extract_data(responses=all_responses)


def save_collection_to_json(
    *,
    objects: List[Dict[str, Any]],
    output_dir: str = "output",
    open_after: bool = False,
    filename_override: Optional[str] = None,
) -> Path:
    """
    Converts and saves a collection of dictionaries to a JSON file.
    Optionally opens the file after saving.
    Returns the path to the saved file.
    """
    if not objects:
        raise ValueError("Cannot serialize an empty list of objects")

    dicts = objects
    file_path = save_dicts_to_json(
        dicts=dicts,
        model_name=filename_override or objects[0].get("index", "collection"),
        license_number=objects[0].get("licenseNumber", ""),
        output_dir=output_dir,
    )

    if open_after:
        open_file(path=file_path)

    return file_path


def save_collection_to_csv(
    *,
    objects: List[Dict[str, Any]],
    output_dir: str = "output",
    open_after: bool = False,
    filename_override: Optional[str] = None,
    strip_empty_columns: bool = False,
) -> Path:
    """
    Converts and saves a collection of dictionaries to a CSV file.
    Optionally opens the file after saving.
    Returns the path to the saved file.
    """
    if not objects:
        raise ValueError("Cannot serialize an empty list of objects")

    dicts = objects
    file_path = save_dicts_to_csv(
        dicts=dicts,
        model_name=filename_override or objects[0].get("index", "collection"),
        license_number=objects[0].get("licenseNumber", ""),
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
    data_loaded_to_db: bool = False


def _generate_default_path(
    *, collection_name: str, license_number: str, extension: str
) -> str:
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
        show_default=False,
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
        extension="csv",
    )

    csv_path = _prompt_for_file_path(proposed_path=default_path, file_type="CSV")

    try:
        # Use file/utils functions to flatten and save directly to user's path
        import csv

        from t3api_utils.file.utils import flatten_dict, prioritized_fieldnames

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


def _action_save_json(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Save collection to JSON with interactive path selection."""
    default_path = _generate_default_path(
        collection_name=state.collection_name,
        license_number=state.license_number,
        extension="json",
    )

    json_path = _prompt_for_file_path(proposed_path=default_path, file_type="JSON")

    try:
        # Save directly to user's chosen path
        import json

        from t3api_utils.file.utils import default_json_serializer

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
                default=lambda obj: default_json_serializer(obj=obj),
            )

        state.json_file_path = json_path
        print_success(f"Saved {len(data)} records to {json_path}")

        # Automatically open the file
        open_file(path=json_path)
        print_success(f"Opened {json_path}")

    except Exception as e:
        print_error(f"Error saving JSON: {e}")


def _action_load_db(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Load collection into database (auto-creates DB connection if needed)."""
    # Check if data has already been loaded in this session
    if state.data_loaded_to_db:
        print_warning("Data has already been loaded into the database in this session.")
        print_info(
            "Use 'Export database schema' to view the existing database structure."
        )
        return

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
        state.data_loaded_to_db = True  # Mark as loaded
        print_success(f"Loaded {len(data)} records into database")
    except Exception as e:
        print_error(f"Error loading data into database: {e}")


def _action_export_schema(*, data: List[Dict[str, Any]], state: _HandlerState) -> None:
    """Export and print database schema (auto-creates connection and loads data if needed)."""
    # Auto-setup: Create database connection if needed
    if not state.db_connection:
        print_progress("Creating database connection...")
        try:
            state.db_connection = create_duckdb_connection()
            print_success("Database connection created")
        except Exception as e:
            print_error(f"Error creating database connection: {e}")
            return

    # Auto-load data if database is empty and data hasn't been loaded yet
    if not _db_has_data(con=state.db_connection):
        if state.data_loaded_to_db:
            print_warning(
                "Database appears empty but data was previously loaded in this session."
            )
            print_info("This might indicate the database connection was reset.")
            return

        print_progress("Database is empty. Loading data automatically...")
        try:
            load_db(con=state.db_connection, data=data)
            state.data_loaded_to_db = True  # Mark as loaded
            print_success(f"Loaded {len(data)} records into database")
        except Exception as e:
            print_error(f"Error loading data into database: {e}")
            return

    try:
        schema = export_duckdb_schema(con=state.db_connection)
        print_subheader("Database Schema")
        console.print(f"[bright_white]{schema}[/bright_white]")
    except Exception as e:
        print_error(f"Error exporting schema: {e}")


def _action_show_help() -> None:
    """Display help information about the collection handler interface."""
    print_subheader("Collection Handler Help")

    help_text = [
        "This interactive interface allows you to work with a collection of data objects.",
        "Each item in your collection contains structured data that you can explore,",
        "filter, export, and analyze using the available menu options.",
        "",
        "Available Actions:",
        "• Inspect collection - Browse and explore individual data items",
        "• Filter by CSV matches - Filter your data based on CSV file criteria",
        "• Save to CSV - Export your data to a CSV file",
        "• Save to JSON - Export your data to a JSON file",
        "• Load into database - Import data into DuckDB for SQL analysis",
        "• Export database schema - View the structure of loaded database tables",
        "• Help - Show this help message",
        "• Exit - Leave the collection handler",
        "",
        "Your collection is automatically named based on the data type and license.",
        "All operations preserve your original data while allowing you to work with",
        "filtered subsets or export to different formats for further analysis.",
    ]

    for line in help_text:
        if line.startswith("•"):
            console.print(f"  [cyan]{line}[/cyan]")
        elif line == "Available Actions:":
            console.print(f"[bold magenta]{line}[/bold magenta]")
        elif line:
            console.print(f"[bright_white]{line}[/bright_white]")
        else:
            console.print()


def _action_inspect_collection(
    *, data: List[Dict[str, Any]], state: _HandlerState
) -> None:
    """Launch collection inspector."""
    inspect_collection(data=data)


def _action_filter_by_csv(
    *, data: List[Dict[str, Any]], state: _HandlerState
) -> List[Dict[str, Any]]:
    """Filter collection by CSV matches and return filtered data."""
    try:
        filtered_data = match_collection_from_csv(
            data=data,
            on_no_match="warn",  # Default to warn for interactive use
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


def _get_menu_options(*, state: _HandlerState) -> List[tuple[str, str, str]]:
    """Get all menu options with descriptions (always show all options, auto-setup handles prerequisites)."""
    options = []

    # Core actions - always available
    options.append(
        ("Inspect collection", "inspect", "Browse and explore data items interactively")
    )
    options.append(
        (
            "Filter by CSV matches",
            "filter_csv",
            "Filter data using criteria from a CSV file",
        )
    )
    options.append(("Save to CSV", "csv", "Export data to a CSV file"))
    options.append(("Save to JSON", "json", "Export data to a JSON file"))
    options.append(
        ("Load into database", "load_db", "Import data into DuckDB for SQL analysis")
    )
    options.append(
        (
            "Export database schema",
            "export_schema",
            "View database table structure (auto-loads data)",
        )
    )
    options.append(("Help", "help", "Show help information about this interface"))
    options.append(("Exit", "exit", "Close the collection handler"))

    return options


def interactive_collection_handler(*, data: List[Dict[str, Any]]) -> None:
    """
    Interactive handler for working with loaded collections.

    Provides a menu-driven interface for saving to files, loading into database,
    exporting schemas, and opening files. State is preserved across operations.
    Automatically extracts collection name and license number from the data.

    Args:
        data: List of dictionaries to work with (must be MetrcObjects)
    """
    if not data:
        print_error("Cannot handle empty collection")
        return

    # Extract metadata from the collection
    collection_name, license_number = extract_collection_metadata(data=data)

    # Initialize state
    state = _HandlerState(
        collection_name=collection_name.lower().replace(" ", "_"),
        license_number=license_number,
    )

    print_header("Collection Handler")

    # Keep track of current working data (may be filtered)
    current_data = data

    def update_data_display() -> None:
        """Update the data display info."""
        if len(current_data) == len(data):
            print_labeled_info(
                "Dataset", f"{collection_name} ({len(current_data):,} items)"
            )
        else:
            print_labeled_info(
                "Dataset",
                f"{collection_name} ({len(current_data):,} items - filtered from {len(data):,})",
            )

    update_data_display()

    # Action mapping - note that some actions return new data
    def get_actions() -> Dict[str, Callable[[], Any]]:
        return {
            "inspect": lambda: _action_inspect_collection(
                data=current_data, state=state
            ),
            "filter_csv": lambda: _action_filter_by_csv(data=current_data, state=state),
            "csv": lambda: _action_save_csv(data=current_data, state=state),
            "json": lambda: _action_save_json(data=current_data, state=state),
            "load_db": lambda: _action_load_db(data=current_data, state=state),
            "export_schema": lambda: _action_export_schema(
                data=current_data, state=state
            ),
            "help": lambda: _action_show_help(),
            "exit": lambda: None,
        }

    while True:
        # Show current state
        state_info = []
        if state.db_connection:
            state_info.append("DB connected")
        if state.data_loaded_to_db:
            state_info.append("Data loaded")
        if state.csv_file_path:
            state_info.append("CSV saved")
        if state.json_file_path:
            state_info.append("JSON saved")

        if state_info:
            print_state_info(state_info)

        # Get and display menu options
        options = _get_menu_options(state=state)

        table = Table(
            title="Collection Handler Options",
            border_style="magenta",
            header_style="bold magenta",
        )
        table.add_column("#", style="magenta", justify="right")
        table.add_column("Action", style="bright_white")
        table.add_column("Description", style="cyan")
        for i, (text, _, description) in enumerate(options, 1):
            table.add_row(str(i), text, description)

        console.print(table)

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
            actions = get_actions()
            action_result = actions[selected_action]()

            # Handle actions that return filtered data
            if selected_action == "filter_csv" and action_result is not None:
                current_data = action_result
                update_data_display()

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


def inspect_collection(*, data: Sequence[Dict[str, Any]]) -> None:
    """
    Interactive inspector for exploring collection objects using Textual TUI.

    Features:
    - Scrollable JSON display with syntax highlighting
    - Mouse and keyboard navigation support
    - Interactive buttons with visual feedback
    - Search functionality with live filtering
    - Professional terminal user interface
    - Responsive layout that adapts to terminal size

    Automatically extracts collection name from the data.
    Args:
        data: List of dictionaries to inspect (must be MetrcObjects)
    """
    if not data:
        print_error("Cannot inspect empty collection")
        return

    # Extract metadata from the collection
    collection_name, _ = extract_collection_metadata(data=data)

    # Import here to avoid circular import
    from t3api_utils.inspector import inspect_collection as textual_inspect

    textual_inspect(data=data, collection_name=collection_name)


def _discover_data_files(
    *,
    search_directory: str,
    file_extensions: List[str],
    include_subdirectories: bool = False,
) -> List[Path]:
    """
    Discover data files in the specified directory.

    Args:
        search_directory: Directory to search
        file_extensions: List of file extensions to include
        include_subdirectories: Whether to search recursively

    Returns:
        List of Path objects for found files, sorted by modification time (newest first)
    """
    search_path = Path(search_directory).resolve()

    if not search_path.exists():
        return []

    found_files: List[Path] = []

    # Create patterns for each extension
    patterns = []
    for ext in file_extensions:
        if not ext.startswith("."):
            ext = f".{ext}"
        if include_subdirectories:
            patterns.append(f"**/*{ext}")
        else:
            patterns.append(f"*{ext}")

    # Find files matching any pattern
    for pattern in patterns:
        found_files.extend(search_path.glob(pattern))

    # Filter out hidden files and directories
    visible_files = [
        f for f in found_files if not any(part.startswith(".") for part in f.parts)
    ]

    # Remove duplicates and sort by modification time (newest first)
    unique_files = list(set(visible_files))
    try:
        unique_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except (OSError, FileNotFoundError):
        # If we can't get stats, just sort by name
        unique_files.sort(key=lambda p: p.name.lower())

    return unique_files


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB"]
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def _format_file_time(timestamp: float) -> str:
    """Format file modification time in readable format."""
    try:
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()

        # If today, show time only
        if dt.date() == now.date():
            return dt.strftime("%H:%M")
        # If this year, show month and day
        elif dt.year == now.year:
            return dt.strftime("%m-%d")
        # Otherwise show year
        else:
            return dt.strftime("%Y")
    except (OSError, ValueError):
        return "Unknown"


def _load_file_content(file_path: Path) -> Dict[str, Any]:
    """
    Load and parse file content based on extension.

    Args:
        file_path: Path to the file to load

    Returns:
        Dictionary with keys: path, content, format, size
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    extension = file_path.suffix.lower()
    file_format = extension[1:] if extension else "unknown"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if extension in [".json"]:
                content = json.load(f)
            elif extension in [".jsonl", ".ndjson"]:
                # JSON Lines format
                content = []
                for line in f:
                    line = line.strip()
                    if line:
                        content.append(json.loads(line))
            elif extension in [".csv", ".tsv"]:
                # Reset file pointer
                f.seek(0)
                delimiter = "\t" if extension == ".tsv" else ","
                reader = csv.DictReader(f, delimiter=delimiter)
                content = list(reader)
            else:
                # Plain text
                f.seek(0)
                content = f.read()

        return {
            "path": file_path,
            "content": content,
            "format": file_format,
            "size": file_path.stat().st_size,
        }

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in file {file_path}: {e}")
    except csv.Error as e:
        raise ValueError(f"Invalid CSV in file {file_path}: {e}")
    except UnicodeDecodeError as e:
        raise ValueError(f"Cannot read file {file_path} as text: {e}")
    except Exception as e:
        raise ValueError(f"Error reading file {file_path}: {e}")


def pick_file(
    *,
    search_directory: str = ".",
    file_extensions: List[str] = [".csv", ".json", ".txt", ".tsv", ".jsonl"],
    include_subdirectories: bool = False,
    allow_custom_path: bool = True,
    load_content: bool = False,
) -> Union[Path, Dict[str, Any]]:
    """
    Interactive file picker for selecting data files.

    Searches the specified directory for files with given extensions and presents
    them in a Rich table picker following the project's CLI standards. Optionally
    allows custom file path input and automatic content loading.

    Args:
        search_directory: Directory to search for files (default: current directory)
        file_extensions: List of file extensions to include (default: common data formats)
        include_subdirectories: Whether to search subdirectories recursively (default: False)
        allow_custom_path: Whether to show "Enter custom path" option (default: True)
        load_content: If True, return file content; if False, return Path object (default: False)

    Returns:
        If load_content=False: Path object pointing to selected file
        If load_content=True: Dict with keys: {"path": Path, "content": Any, "format": str, "size": int}

    Raises:
        typer.Exit: If user cancels or no files found and custom path not allowed
        FileNotFoundError: If custom path doesn't exist
        ValueError: If file cannot be read or parsed
    """
    print_subheader("File Picker")

    # Discover files
    found_files = _discover_data_files(
        search_directory=search_directory,
        file_extensions=file_extensions,
        include_subdirectories=include_subdirectories,
    )

    # Prepare options list
    options: List[tuple[str, str, str, str, Path]] = (
        []
    )  # display_name, size, modified, type, path

    for file_path in found_files:
        try:
            stat = file_path.stat()
            size_str = _format_file_size(stat.st_size)
            modified_str = _format_file_time(stat.st_mtime)
            file_type = file_path.suffix[1:].upper() if file_path.suffix else "FILE"

            # Show relative path if it's shorter, otherwise show name only
            try:
                rel_path = file_path.relative_to(Path(search_directory))
                display_name = str(rel_path)
            except ValueError:
                display_name = file_path.name

            options.append((display_name, size_str, modified_str, file_type, file_path))

        except (OSError, FileNotFoundError):
            # Skip files we can't access
            continue

    # Add custom path option if enabled
    if allow_custom_path:
        options.append(("Enter custom path...", "", "", "CUSTOM", Path("")))

    # Check if we have any options
    if not options:
        if allow_custom_path:
            print_warning("No files found in directory. Please enter a custom path.")
            return _handle_custom_path_input(load_content=load_content)
        else:
            print_error("No data files found in the specified directory.")
            raise typer.Exit(code=1)

    # Create and display table following CLI picker standards
    table = Table(
        title="Available Data Files",
        border_style="magenta",
        header_style="bold magenta",
    )
    table.add_column("#", style="magenta", justify="right")
    table.add_column("File", style="bright_white")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Modified", style="cyan", justify="right")
    table.add_column("Type", style="cyan", justify="center")

    for idx, (display_name, size_str, modified_str, file_type, _) in enumerate(
        options, start=1
    ):
        table.add_row(str(idx), display_name, size_str, modified_str, file_type)

    console.print(table)

    # Get user choice
    while True:
        try:
            choice = typer.prompt("Select file (number)", type=int)
            if 1 <= choice <= len(options):
                selected_option = options[choice - 1]

                # Handle custom path option
                if selected_option[4] == Path(""):  # Custom path marker
                    return _handle_custom_path_input(load_content=load_content)

                # Handle regular file selection
                selected_path: Path = selected_option[4]
                print_success(f"Selected: {selected_path}")

                if load_content:
                    print_progress("Loading file content...")
                    try:
                        file_data = _load_file_content(selected_path)
                        print_success(
                            f"Loaded {file_data['format'].upper()} file ({_format_file_size(file_data['size'])})"
                        )
                        return file_data
                    except Exception as e:
                        print_error(f"Error loading file: {e}")
                        raise
                else:
                    return selected_path

            else:
                print_error(f"Invalid selection. Please choose 1-{len(options)}.")

        except (ValueError, typer.Abort, KeyboardInterrupt):
            print_error("Invalid input or operation cancelled.")
            raise typer.Exit(code=1)


def _handle_custom_path_input(*, load_content: bool) -> Union[Path, Dict[str, Any]]:
    """Handle custom file path input."""
    print_subheader("Custom File Path")

    while True:
        try:
            path_input = typer.prompt("Enter file path")
            file_path = Path(path_input.strip()).expanduser().resolve()

            if not file_path.exists():
                print_error("File does not exist. Please try again.")
                continue

            if not file_path.is_file():
                print_error("Path is not a file. Please try again.")
                continue

            print_success(f"Selected: {file_path}")

            if load_content:
                print_progress("Loading file content...")
                try:
                    file_data = _load_file_content(file_path)
                    print_success(
                        f"Loaded {file_data['format'].upper()} file ({_format_file_size(file_data['size'])})"
                    )
                    return file_data
                except Exception as e:
                    print_error(f"Error loading file: {e}")
                    # Ask if user wants to try a different path
                    try_again = typer.confirm("Try a different file?")
                    if not try_again:
                        raise typer.Exit(code=1)
                    continue
            else:
                return file_path

        except (typer.Abort, KeyboardInterrupt):
            print_error("Operation cancelled.")
            raise typer.Exit(code=1)


def match_collection_from_csv(
    *,
    data: List[Dict[str, Any]],
    on_no_match: Literal["error", "warn", "skip"] = "warn",
) -> List[Dict[str, Any]]:
    """
    Filter a collection by matching entries from a CSV file.

    Uses the file picker to select a CSV file, then finds exact matches between
    CSV rows and collection items. CSV column headers must exactly match
    collection field names. Automatically extracts collection name from the data.

    Args:
        data: The existing collection to search within
        on_no_match: Behavior when CSV row doesn't match any collection item

    Returns:
        Filtered subset of data containing only matched items

    Raises:
        ValueError: If CSV columns don't match collection fields
        typer.Exit: If user cancels file selection
        FileNotFoundError: If CSV file cannot be loaded

    Example CSV format (columns must match collection fields exactly):
    ```csv
    id,name,status
    12345,ProductA,Active
    67890,ProductB,Inactive
    ```
    """
    if not data:
        print_error("Cannot match against empty collection")
        raise ValueError("Collection data cannot be empty")

    # Extract metadata from the collection
    collection_name, _ = extract_collection_metadata(data=data)

    print_subheader(f"CSV Matching for {collection_name.title()}")

    # Use file picker to load CSV
    print_info("Select CSV file with matching criteria...")
    try:
        csv_file_data = pick_file(
            file_extensions=[".csv", ".tsv"], load_content=True, search_directory="."
        )
    except typer.Exit:
        print_error("File selection cancelled")
        raise

    if not isinstance(csv_file_data, dict) or "content" not in csv_file_data:
        print_error("Failed to load CSV content")
        raise ValueError("CSV file could not be loaded with content")

    csv_content = csv_file_data["content"]

    if not csv_content:
        print_error("CSV file is empty")
        raise ValueError("CSV file contains no data")

    # Validate CSV structure
    if not isinstance(csv_content, list) or not csv_content[0]:
        print_error("Invalid CSV format - expected list of dictionaries")
        raise ValueError("CSV must contain headers and data rows")

    # Get CSV columns and collection fields
    csv_columns = set(csv_content[0].keys())
    collection_fields = set(data[0].keys())

    print_labeled_info("CSV columns", ", ".join(sorted(csv_columns)))
    print_labeled_info("Collection fields", ", ".join(sorted(collection_fields)))

    # Early exit: Check if all CSV columns exist in collection
    missing_fields = csv_columns - collection_fields
    if missing_fields:
        error_msg = f"CSV columns not found in collection: {sorted(missing_fields)}"
        print_error(error_msg)
        raise ValueError(error_msg)

    print_success("✓ All CSV columns found in collection")

    # Process matches
    matched_items: List[Dict[str, Any]] = []
    unmatched_csv_rows: List[Dict[str, Any]] = []

    print_progress(f"Processing {len(csv_content)} CSV rows...")

    for row_idx, csv_row in enumerate(csv_content, start=1):
        # Find exact matches in collection
        matches = [
            item
            for item in data
            if all(
                str(item.get(col, "")) == str(csv_row.get(col, ""))
                for col in csv_columns
            )
        ]

        if matches:
            # Add all matches (could be multiple items matching the same CSV row)
            matched_items.extend(matches)
        else:
            unmatched_csv_rows.append(csv_row)

            # Handle unmatched based on parameter
            if on_no_match == "error":
                error_msg = f"No match found for CSV row {row_idx}: {csv_row}"
                print_error(error_msg)
                raise ValueError(error_msg)
            elif on_no_match == "warn":
                print_warning(f"No match found for CSV row {row_idx}: {csv_row}")

    # Remove duplicates while preserving order
    seen_items = set()
    unique_matched_items = []
    for item in matched_items:
        # Create a hashable key from the item (using str representation)
        item_key = str(sorted(item.items()))
        if item_key not in seen_items:
            seen_items.add(item_key)
            unique_matched_items.append(item)

    # Display results summary
    print_subheader("Matching Results")
    print_labeled_info("CSV rows processed", str(len(csv_content)))
    print_labeled_info("Matches found", str(len(unique_matched_items)))
    print_labeled_info("Unmatched CSV rows", str(len(unmatched_csv_rows)))
    print_labeled_info("Original collection size", str(len(data)))

    if unique_matched_items:
        percentage = (len(unique_matched_items) / len(data)) * 100
        print_labeled_info(
            "Filtered collection size",
            f"{len(unique_matched_items)} ({percentage:.1f}%)",
        )
        print_success(f"✓ Successfully filtered {collection_name}")
    else:
        print_warning("No matches found - returning empty collection")

    return unique_matched_items


def extract_collection_metadata(*, data: Sequence[Dict[str, Any]]) -> tuple[str, str]:
    """Extract collection name and license number from a collection of MetrcObjects.

    For collection name: Uses dataModel__index format when index is present,
    otherwise just dataModel. If multiple different values exist, returns "mixed_datamodels".

    For license number: Uses the licenseNumber field. If multiple different values
    exist, returns "mixed_licenses".

    Args:
        collection: List of MetrcObject instances to analyze

    Returns:
        Tuple of (collection_name, license_number)

    Examples:
        >>> objects = [
        ...     {"dataModel": "PACKAGE", "index": "active", "licenseNumber": "CUL00001"},
        ...     {"dataModel": "PACKAGE", "index": "active", "licenseNumber": "CUL00001"}
        ... ]
        >>> extract_collection_metadata(objects)
        ("PACKAGE__active", "CUL00001")

        >>> mixed_objects = [
        ...     {"dataModel": "PACKAGE", "licenseNumber": "CUL00001"},
        ...     {"dataModel": "PLANT", "licenseNumber": "CUL00002"}
        ... ]
        >>> extract_collection_metadata(mixed_objects)
        ("mixed_datamodels", "mixed_licenses")
    """
    if not data:
        return ("empty_collection", "no_license")

    # Extract collection names (dataModel__index or dataModel)
    collection_names = set()
    license_numbers = set()

    for obj in data:
        # Build collection name
        data_model = obj.get("dataModel", "unknown_datamodel")
        index = obj.get("index")

        if index:
            collection_name = f"{data_model}__{index}"
        else:
            collection_name = data_model

        collection_names.add(collection_name)

        # Extract license number
        license_number = obj.get("licenseNumber", "unknown_license")
        license_numbers.add(license_number)

    # Determine final names
    if len(collection_names) == 1:
        final_collection_name = next(iter(collection_names))
    else:
        final_collection_name = "mixed_datamodels"

    if len(license_numbers) == 1:
        final_license_number = next(iter(license_numbers))
    else:
        final_license_number = "mixed_licenses"

    return (final_collection_name, final_license_number)
