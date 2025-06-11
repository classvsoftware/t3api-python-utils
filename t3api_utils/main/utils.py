import typer
from rich.console import Console
from rich.table import Table
from t3api import ApiClient
from t3api.api.licenses_api import LicensesApi
from t3api.models.v2_licenses_get200_response_inner import \
    V2LicensesGet200ResponseInner

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.auth.utils import \
    create_credentials_authenticated_client_or_error
from t3api_utils.cli.utils import resolve_auth_inputs_or_error
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.logging import get_logger

console = Console()

logger = get_logger(__name__)

def get_authenticated_client_or_error() -> ApiClient:
    """
    High-level method to return an authenticated client.
    Handles CLI prompts, .env, and validation internally.
    Raises AuthenticationError or generic Exception on failure.
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


def pick_license(*, api_client: ApiClient) -> V2LicensesGet200ResponseInner:
    response = LicensesApi(api_client=api_client).v2_licenses_get()

    if not response:
        typer.echo("No licenses found.")
        raise typer.Exit(code=1)

    table = Table(title="Available Licenses")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("License Name", style="magenta")
    table.add_column("License Number", style="green")

    for idx, license in enumerate(response, start=1):
        table.add_row(str(idx), license.license_name, license.license_number)

    console.print(table)

    choice = typer.prompt(f"Select a license", type=int)

    if choice < 1 or choice > len(response):
        typer.echo("Invalid selection.")
        raise typer.Exit(code=1)

    selected_license = response[choice - 1]
    return selected_license