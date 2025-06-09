import os
from typing import cast

import typer
from dotenv import load_dotenv, set_key

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.cli.consts import (DEFAULT_ENV_PATH, OTP_WHITELIST,
                                    REQUIRED_ENV_KEYS, EnvKeys)
from t3api_utils.exceptions import AuthenticationError


def is_env_file_complete() -> bool:
    if not os.path.exists(DEFAULT_ENV_PATH):
        return False

    load_dotenv(dotenv_path=DEFAULT_ENV_PATH)

    for key in REQUIRED_ENV_KEYS:
        if not os.getenv(key):
            return False

    return True


def load_credentials_from_env_or_error() -> T3Credentials:
    hostname = (os.getenv(EnvKeys.METRC_HOSTNAME.value) or "").strip()
    username = (os.getenv(EnvKeys.METRC_USERNAME.value) or "").strip()
    password = (os.getenv(EnvKeys.METRC_PASSWORD.value) or "").strip()

    if not hostname:
        raise AuthenticationError("Missing or empty environment variable: METRC_HOSTNAME")
    if not username:
        raise AuthenticationError("Missing or empty environment variable: METRC_USERNAME")
    if not password:
        raise AuthenticationError("Missing or empty environment variable: METRC_PASSWORD")

    return {
        "hostname": hostname,
        "username": username,
        "password": password,
        "otp": None
    }


def offer_to_save_credentials(*, credentials: T3Credentials) -> None:
    if not typer.confirm(
        f"Save these values to {DEFAULT_ENV_PATH} for future use?", default=True
    ):
        return

    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME, credentials["hostname"])
    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME, credentials["username"])
    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD, credentials["password"])



def prompt_for_credentials_or_error() -> T3Credentials:
    hostname = typer.prompt(
        "Enter Metrc hostname (e.g., mo.metrc.com)",
        default=os.getenv(EnvKeys.METRC_HOSTNAME, "").strip() or None,
    )
    username = typer.prompt(
        "Enter T3 API username",
        default=os.getenv(EnvKeys.METRC_USERNAME, "").strip() or None,
    )
    password = typer.prompt(
        "Enter T3 API password",
        default=os.getenv(EnvKeys.METRC_PASSWORD, "").strip() or None,
        hide_input=True,
    )

    credentials: T3Credentials = {
        "hostname": hostname,
        "username": username,
        "password": password,
        "otp": None,
    }

    if hostname in OTP_WHITELIST:
        otp = typer.prompt("Enter 6-digit T3 OTP")

        if not otp or len(otp) != 6 or not otp.isdigit():
            raise AuthenticationError(f"Invalid OTP: {otp}")

        credentials["otp"] = otp

    for key, value in credentials.items():
        if key != "otp" and (not isinstance(value, str) or not value.strip()):
            raise AuthenticationError(f"Missing or empty credential: {key}")

    return credentials


def resolve_auth_inputs_or_error() -> T3Credentials:
    credentials = prompt_for_credentials_or_error()
    
    offer_to_save_credentials(credentials=credentials)
    
    return credentials