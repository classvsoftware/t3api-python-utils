import os
from typing import Dict

import typer
from dotenv import load_dotenv, set_key

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.cli.consts import DEFAULT_ENV_PATH, OTP_WHITELIST, EnvKeys
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.logging import get_logger

logger = get_logger(__name__)


def load_credentials_from_env() -> Dict[str, str]:
    """
    Load credential values from the environment file (.env).
    """
    load_dotenv(dotenv_path=DEFAULT_ENV_PATH)

    creds = {}
    hostname = (os.getenv(EnvKeys.METRC_HOSTNAME.value) or "").strip()
    username = (os.getenv(EnvKeys.METRC_USERNAME.value) or "").strip()
    password = (os.getenv(EnvKeys.METRC_PASSWORD.value) or "").strip()

    if hostname:
        creds["hostname"] = hostname
    if username:
        creds["username"] = username
    if password:
        creds["password"] = password

    return creds


def offer_to_save_credentials(*, credentials: T3Credentials) -> None:
    """
    Offer to save credentials to the .env file if it's missing or out-of-date.
    """
    load_dotenv(dotenv_path=DEFAULT_ENV_PATH)
    env_exists = os.path.exists(DEFAULT_ENV_PATH)

    current_hostname = os.getenv(EnvKeys.METRC_HOSTNAME.value, "").strip()
    current_username = os.getenv(EnvKeys.METRC_USERNAME.value, "").strip()
    current_password = os.getenv(EnvKeys.METRC_PASSWORD.value, "").strip()

    hostname_differs = credentials["hostname"] != current_hostname
    username_differs = credentials["username"] != current_username
    password_differs = credentials["password"] != current_password

    if not env_exists:
        if typer.confirm(
            f"No credentials file found. Save these values to [bold]{DEFAULT_ENV_PATH}[/]?", default=True
        ):
            logger.info("[green]Saving credentials to new environment file.[/green]")
            set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME.value, credentials["hostname"])
            set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME.value, credentials["username"])
            set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD.value, credentials["password"])
    elif hostname_differs or username_differs or password_differs:
        if typer.confirm(
            f"Some credential values differ from those in [bold]{DEFAULT_ENV_PATH}[/]. Update them?", default=True
        ):
            logger.info("[cyan]Updating credentials in environment file.[/cyan]")
            set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME.value, credentials["hostname"])
            set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME.value, credentials["username"])
            set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD.value, credentials["password"])


def prompt_for_credentials_or_error(**kwargs) -> T3Credentials:
    """
    Prompt for any missing credentials, using provided values if available.
    """
    hostname = kwargs.get("hostname")
    username = kwargs.get("username")
    password = kwargs.get("password")

    if hostname:
        logger.info(f"[blue]Using stored value for hostname:[/] {hostname}")
    else:
        hostname = typer.prompt("Enter Metrc hostname (e.g., mo.metrc.com)")

    if username:
        logger.info(f"[blue]Using stored value for username:[/] {username}")
    else:
        username = typer.prompt("Enter T3 API username")

    if password:
        logger.info("[blue]Using stored value for password.[/]")
    else:
        password = typer.prompt("Enter T3 API password", hide_input=True)

    credentials: T3Credentials = {
        "hostname": hostname,
        "username": username,
        "password": password,
        "otp": None,
    }

    if hostname in OTP_WHITELIST:
        otp = typer.prompt("Enter 6-digit T3 OTP")
        if not otp or len(otp) != 6 or not otp.isdigit():
            logger.error("[red]Invalid OTP entered.[/red]")
            raise AuthenticationError(f"Invalid OTP: {otp}")
        credentials["otp"] = otp

    for key, value in credentials.items():
        if key != "otp" and (not isinstance(value, str) or not value.strip()):
            logger.error(f"[red]Missing or empty credential:[/] {key}")
            raise AuthenticationError(f"Missing or empty credential: {key}")

    return credentials


def resolve_auth_inputs_or_error() -> T3Credentials:
    """
    Resolve authentication credentials from env and/or prompt and offer to save.
    """
    stored_credentials = load_credentials_from_env()
    credentials = prompt_for_credentials_or_error(**stored_credentials)
    offer_to_save_credentials(credentials=credentials)
    return credentials
