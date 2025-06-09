import os

import typer
from dotenv import load_dotenv, set_key

from t3api_utils.auth.interfaces import T3Credentials, T3StoredCredentials
from t3api_utils.cli.consts import (
    DEFAULT_ENV_PATH,
    OTP_WHITELIST,
    REQUIRED_ENV_KEYS,
    EnvKeys,
)
from t3api_utils.exceptions import AuthenticationError


def is_env_file_complete() -> bool:
    if not os.path.exists(DEFAULT_ENV_PATH):
        return False

    load_dotenv(dotenv_path=DEFAULT_ENV_PATH)

    for key in REQUIRED_ENV_KEYS:
        if not os.getenv(key):
            return False

    return True


def load_credentials_from_env_or_error() -> T3StoredCredentials:
    creds: T3StoredCredentials = {
        "hostname": os.getenv(EnvKeys.METRC_HOSTNAME),
        "username": os.getenv(EnvKeys.METRC_USERNAME),
        "password": os.getenv(EnvKeys.METRC_PASSWORD),
    }

    for key, value in creds.items():
        if not value or not value.strip():
            raise AuthenticationError(f"Missing or empty environment variable: {key}")

    return creds


def prompt_for_credentials_or_error() -> T3Credentials:
    hostname = typer.prompt("Enter Metrc hostname (e.g., mo.metrc.com)")
    username = typer.prompt("Enter T3 API username")
    password = typer.prompt("Enter T3 API password", hide_input=True)

    creds: T3Credentials = {
        "hostname": hostname,
        "username": username,
        "password": password,
    }

    if hostname in OTP_WHITELIST:
        otp = typer.prompt("Enter 6-digit T3 OTP")

        if not otp or len(otp) != 6:
            raise AuthenticationError(f"Invalid OTP: {otp}")

        creds["otp"] = otp

    for key, value in creds.items():
        if key != "otp" and (not value or not value.strip()):
            raise AuthenticationError(f"Missing or empty credential: {key}")

    offer_to_save_credentials(creds)

    return creds


def offer_to_save_credentials(creds: T3Credentials) -> None:
    if not typer.confirm(
        f"Save these values to {DEFAULT_ENV_PATH} for future use?", default=True
    ):
        return

    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME, creds["hostname"])
    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME, creds["username"])
    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD, creds["password"])


def resolve_auth_inputs_or_error() -> T3Credentials:
    if is_env_file_complete():
        return load_credentials_from_env_or_error()

    creds = prompt_for_credentials_or_error()
    return creds
