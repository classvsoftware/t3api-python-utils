import os
from typing import Dict, Optional

import typer
from dotenv import load_dotenv, set_key

from t3api_utils.cli.consts import (
    DEFAULT_ENV_PATH,
    OTP_WHITELIST,
    REQUIRED_ENV_KEYS,
    EnvKeys,
)


def resolve_auth_inputs() -> Dict[str, Optional[str]]:
    if is_env_file_complete():
        return load_credentials_from_env()

    creds = prompt_for_credentials()
    offer_to_save_credentials(creds)
    return creds


def is_env_file_complete() -> bool:
    if not os.path.exists(DEFAULT_ENV_PATH):
        return False

    load_dotenv(dotDEFAULT_ENV_PATH=DEFAULT_ENV_PATH)

    for key in REQUIRED_ENV_KEYS:
        if not os.getenv(key):
            return False

    return True


def load_credentials_from_env() -> Dict[str, Optional[str]]:
    return {
        "hostname": os.getenv(EnvKeys.METRC_HOSTNAME),
        "username": os.getenv(EnvKeys.METRC_USERNAME),
        "password": os.getenv(EnvKeys.METRC_PASSWORD),
    }


def prompt_for_credentials() -> Dict[str, Optional[str]]:
    hostname = typer.prompt("Enter Metrc hostname (e.g., mo.metrc.com)")
    username = typer.prompt("Enter T3 API username")
    password = typer.prompt("Enter T3 API password", hide_input=True)

    otp = None
    if hostname in OTP_WHITELIST:
        otp = typer.prompt("Enter 6-digit T3 OTP")

    return {
        "hostname": hostname,
        "username": username,
        "password": password,
        "otp": otp,
    }


def offer_to_save_credentials(creds: Dict[str, Optional[str]]) -> None:
    if not typer.confirm(
        f"Save these values to {DEFAULT_ENV_PATH} for future use?", default=True
    ):
        return

    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME, creds["hostname"])
    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME, creds["username"])
    set_key(DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD, creds["password"])
