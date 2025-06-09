import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from t3api_utils.cli import utils
from t3api_utils.cli.consts import DEFAULT_ENV_PATH, EnvKeys


@patch("os.path.exists", return_value=False)
def test_is_env_file_complete_missing_env_file(mock_exists):
    assert not utils.is_env_file_complete()


@patch("os.path.exists", return_value=True)
@patch("t3api_utils.cli.utils.load_dotenv")
@patch(
    "os.getenv", side_effect=lambda k: "value" if k in utils.REQUIRED_ENV_KEYS else None
)
def test_is_env_file_complete_success(mock_getenv, mock_load_dotenv, mock_exists):
    assert utils.is_env_file_complete()


@patch(
    "t3api_utils.cli.utils.os.getenv",
    side_effect=lambda x: None if x == EnvKeys.METRC_USERNAME else "value",
)
@patch("t3api_utils.cli.utils.load_dotenv")
@patch("t3api_utils.cli.utils.os.path.exists", return_value=True)
def test_is_env_file_complete_missing_key(mock_exists, mock_load_dotenv, mock_getenv):
    assert not utils.is_env_file_complete()


@patch.dict(
    os.environ,
    {
        EnvKeys.METRC_HOSTNAME: "mo.metrc.com",
        EnvKeys.METRC_USERNAME: "user",
        EnvKeys.METRC_PASSWORD: "pass",
    },
)
def test_load_credentials_from_env():
    creds = utils.load_credentials_from_env()
    assert creds == {"hostname": "mo.metrc.com", "username": "user", "password": "pass"}


@patch("typer.prompt")
def test_prompt_for_credentials_with_otp(mock_prompt):
    mock_prompt.side_effect = ["mi.metrc.com", "user", "pass", "123456"]
    result = utils.prompt_for_credentials()
    assert result == {
        "hostname": "mi.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": "123456",
    }


@patch("typer.prompt")
def test_prompt_for_credentials_without_otp(mock_prompt):
    mock_prompt.side_effect = ["somewhere.com", "user", "pass"]
    result = utils.prompt_for_credentials()
    assert result == {
        "hostname": "somewhere.com",
        "username": "user",
        "password": "pass",
        "otp": None,
    }


@patch("typer.confirm", return_value=True)
@patch("t3api_utils.cli.utils.set_key")
def test_offer_to_save_credentials(mock_set_key, mock_confirm):
    creds = {"hostname": "mo.metrc.com", "username": "user", "password": "pass"}
    utils.offer_to_save_credentials(creds)
    assert mock_set_key.call_count == 3


@patch("t3api_utils.cli.utils.is_env_file_complete", return_value=True)
@patch("t3api_utils.cli.utils.load_credentials_from_env")
def test_resolve_auth_inputs_from_env(mock_load, mock_check):
    mock_load.return_value = {"hostname": "x", "username": "y", "password": "z"}
    result = utils.resolve_auth_inputs()
    assert result["hostname"] == "x"
    mock_load.assert_called_once()


@patch("t3api_utils.cli.utils.is_env_file_complete", return_value=False)
@patch("t3api_utils.cli.utils.prompt_for_credentials")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_resolve_auth_inputs_from_prompt(mock_save, mock_prompt, mock_check):
    mock_prompt.return_value = {
        "hostname": "x",
        "username": "y",
        "password": "z",
        "otp": None,
    }
    result = utils.resolve_auth_inputs()
    assert result["hostname"] == "x"
    mock_save.assert_called_once()
