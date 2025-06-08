import os
from typing import Dict, Optional

import typer
from dotenv import load_dotenv, set_key

from t3api_utils.consts import ENV_PATH, OTP_ENV_KEY, OTP_WHITELIST, REQUIRED_ENV_KEYS


def resolve_auth_inputs() -> Dict[str, Optional[str]]:
    if is_env_file_complete():
        return load_credentials_from_env()

    creds = prompt_for_credentials()
    offer_to_save_credentials(creds)
    return creds


def resolve_auth_inputs_or_error() -> Dict[str, Optional[str]]:
    if not is_env_file_complete():
        raise RuntimeError(
            f"{ENV_PATH} is missing or incomplete. Cannot proceed without credentials."
        )
    return load_credentials_from_env()


def is_env_file_complete() -> bool:
    if not os.path.exists(ENV_PATH):
        return False

    load_dotenv(dotenv_path=ENV_PATH)

    for key in REQUIRED_ENV_KEYS:
        if not os.getenv(key):
            return False

    hostname = os.getenv("T3_HOSTNAME")
    if hostname in OTP_WHITELIST and not os.getenv(OTP_ENV_KEY):
        return False

    return True


def load_credentials_from_env() -> Dict[str, Optional[str]]:
    return {
        "hostname": os.getenv("T3_HOSTNAME"),
        "username": os.getenv("T3_USERNAME"),
        "password": os.getenv("T3_PASSWORD"),
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
        f"Save these values to {ENV_PATH} for future use?", default=True
    ):
        return

    set_key(ENV_PATH, "T3_HOSTNAME", creds["hostname"])
    set_key(ENV_PATH, "T3_USERNAME", creds["username"])
    set_key(ENV_PATH, "T3_PASSWORD", creds["password"])
