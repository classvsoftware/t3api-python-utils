import os
from unittest.mock import patch

import pytest

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.cli import utils as cli
from t3api_utils.cli.consts import REQUIRED_ENV_KEYS, EnvKeys
from t3api_utils.exceptions import AuthenticationError


@patch.dict(os.environ, {
    EnvKeys.METRC_HOSTNAME.value: "mo.metrc.com",
    EnvKeys.METRC_USERNAME.value: "user",
    EnvKeys.METRC_PASSWORD.value: "pass",
})
def test_load_credentials_from_env():
    credentials = cli.load_credentials_from_env()
    assert credentials == {
        "hostname": "mo.metrc.com",
        "username": "user",
        "password": "pass",
    }


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_with_otp(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["mi.metrc.com", "user", "pass", "123456"]
    result = cli.prompt_for_credentials_or_error()
    assert result == {
        "hostname": "mi.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": "123456",
    }


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_without_otp(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["somewhere.com", "user", "pass"]
    result = cli.prompt_for_credentials_or_error()
    assert result == {
        "hostname": "somewhere.com",
        "username": "user",
        "password": "pass",
        "otp": None,
    }


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_invalid_otp_raises(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["mi.metrc.com", "user", "pass", "abc"]
    with pytest.raises(AuthenticationError, match="Invalid OTP"):
        cli.prompt_for_credentials_or_error()


@patch("typer.confirm", return_value=True)
@patch("t3api_utils.cli.utils.set_key")
def test_offer_to_save_credentials(mock_set_key, mock_confirm):
    credentials: T3Credentials = {
        "hostname": "mo.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": None,
    }
    cli.offer_to_save_credentials(credentials=credentials)
    assert mock_set_key.call_count == 3
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME, "mo.metrc.com")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME, "user")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD, "pass")


@patch("t3api_utils.cli.utils.prompt_for_credentials_or_error")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_resolve_auth_inputs_from_prompt(mock_save_credentials, mock_prompt):
    mock_prompt.return_value = {
        "hostname": "x",
        "username": "y",
        "password": "z",
        "otp": None,
    }
    result = cli.resolve_auth_inputs_or_error()
    assert result["hostname"] == "x"
    mock_save_credentials.assert_called_once()
    mock_prompt.assert_called_once()
