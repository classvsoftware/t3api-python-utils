import os
from typing import Dict

import typer
from dotenv import load_dotenv, set_key

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.cli.consts import DEFAULT_ENV_PATH, OTP_WHITELIST, CREDENTIAL_EMAIL_WHITELIST, EnvKeys
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.logging import get_logger
from t3api_utils.style import print_error, print_info, print_subheader

__all__ = ["DEFAULT_ENV_PATH", "load_credentials_from_env", "offer_to_save_credentials", "prompt_for_credentials_or_error", "resolve_auth_inputs_or_error"]

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
    email = (os.getenv(EnvKeys.METRC_EMAIL.value) or "").strip()

    if hostname:
        creds["hostname"] = hostname
    if username:
        creds["username"] = username
    if password:
        creds["password"] = password
    if email:
        creds["email"] = email

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
    current_email = os.getenv(EnvKeys.METRC_EMAIL.value, "").strip()

    hostname_differs = credentials["hostname"] != current_hostname
    username_differs = credentials["username"] != current_username
    password_differs = credentials["password"] != current_password

    # Only check email differences if the hostname requires email
    email_differs = False
    if credentials["hostname"] in CREDENTIAL_EMAIL_WHITELIST:
        email_differs = credentials.get("email") != current_email

    if not env_exists:
        if typer.confirm(
            f"No credentials file found. Save these values to {DEFAULT_ENV_PATH}?",
            default=True,
        ):
            logger.info("[green]Saving credentials to new environment file.[/green]")
            set_key(
                DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME.value, credentials["hostname"]
            )
            set_key(
                DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME.value, credentials["username"]
            )
            set_key(
                DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD.value, credentials["password"]
            )
            email_value = credentials.get("email")
            if email_value:
                set_key(
                    DEFAULT_ENV_PATH, EnvKeys.METRC_EMAIL.value, email_value
                )
    elif hostname_differs or username_differs or password_differs or email_differs:
        if typer.confirm(
            f"Some credential values differ from those in {DEFAULT_ENV_PATH}. Update them?",
            default=True,
        ):
            logger.info("[cyan]Updating credentials in environment file.[/cyan]")
            set_key(
                DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME.value, credentials["hostname"]
            )
            set_key(
                DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME.value, credentials["username"]
            )
            set_key(
                DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD.value, credentials["password"]
            )
            email_value = credentials.get("email")
            if email_value:
                set_key(
                    DEFAULT_ENV_PATH, EnvKeys.METRC_EMAIL.value, email_value
                )


def prompt_for_credentials_or_error(**kwargs: object) -> T3Credentials:
    """
    Prompt for any missing credentials, using provided values if available.
    """
    hostname = str(kwargs.get("hostname", "")) if kwargs.get("hostname") else None
    username = str(kwargs.get("username", "")) if kwargs.get("username") else None
    password = str(kwargs.get("password", "")) if kwargs.get("password") else None
    email = str(kwargs.get("email", "")) if kwargs.get("email") else None

    if hostname:
        print_info(f"Using stored value for hostname: {hostname}")
    else:
        hostname = typer.prompt("Enter Metrc hostname (e.g., mo.metrc.com)")

    if username:
        print_info(f"Using stored value for username: {username}")
    else:
        username = typer.prompt("Enter Metrc username")

    if password:
        print_info("Using stored value for password.")
    else:
        password = typer.prompt("Enter Metrc password", hide_input=True)

    credentials: T3Credentials = {
        "hostname": hostname or "",
        "username": username or "",
        "password": password or "",
        "otp": None,
        "email": None,
    }

    if hostname in OTP_WHITELIST:
        otp = typer.prompt("Enter 6-digit Metrc 2-factor authentication code")
        if not otp or len(otp) != 6 or not otp.isdigit():
            print_error("Invalid 2-factor authentication entered.")
            raise AuthenticationError(f"Invalid 2-factor authentication: {otp}")
        credentials["otp"] = otp

    if hostname in CREDENTIAL_EMAIL_WHITELIST:
        if email:
            print_info(f"Using stored value for email: {email}")
            credentials["email"] = email
        else:
            email_input = typer.prompt("Enter Metrc email address")
            if not email_input or "@" not in email_input:
                print_error("Invalid email address entered.")
                raise AuthenticationError(f"Invalid email address: {email_input}")
            credentials["email"] = email_input

    for key, value in credentials.items():
        if key not in ("otp", "email") and (not isinstance(value, str) or not value.strip()):
            print_error(f"Missing or empty credential: {key}")
            raise AuthenticationError(f"Missing or empty credential: {key}")

    return credentials


def resolve_auth_inputs_or_error() -> T3Credentials:
    """
    Resolve authentication credentials from env and/or prompt and offer to save.
    """
    print_subheader("Authentication Required")
    stored_credentials = load_credentials_from_env()
    credentials = prompt_for_credentials_or_error(**stored_credentials)
    offer_to_save_credentials(credentials=credentials)
    return credentials
