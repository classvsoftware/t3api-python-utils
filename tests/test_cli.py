import os
from unittest.mock import patch

import pytest

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.cli import utils as cli
from t3api_utils.cli.consts import EnvKeys
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


@patch.dict(os.environ, {
    EnvKeys.METRC_HOSTNAME.value: "co.metrc.com",
    EnvKeys.METRC_USERNAME.value: "user",
    EnvKeys.METRC_PASSWORD.value: "pass",
    EnvKeys.METRC_EMAIL.value: "test@example.com",
})
def test_load_credentials_from_env_with_email():
    credentials = cli.load_credentials_from_env()
    assert credentials == {
        "hostname": "co.metrc.com",
        "username": "user",
        "password": "pass",
        "email": "test@example.com",
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
        "email": None,
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
        "email": None,
    }


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_invalid_otp_raises(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["mi.metrc.com", "user", "pass", "abc"]
    with pytest.raises(AuthenticationError, match="Invalid 2-factor authentication"):
        cli.prompt_for_credentials_or_error()


@patch("typer.confirm", return_value=True)
@patch("t3api_utils.cli.utils.set_key")
def test_offer_to_save_credentials(mock_set_key, mock_confirm):
    credentials: T3Credentials = {
        "hostname": "mo.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": None,
    }
    cli.offer_to_save_credentials(credentials=credentials)
    assert mock_set_key.call_count == 3
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME, "mo.metrc.com")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME, "user")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD, "pass")


@patch("typer.confirm", return_value=True)
@patch("t3api_utils.cli.utils.set_key")
def test_offer_to_save_credentials_with_email(mock_set_key, mock_confirm):
    credentials: T3Credentials = {
        "hostname": "co.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": "test@example.com",
    }
    cli.offer_to_save_credentials(credentials=credentials)
    assert mock_set_key.call_count == 4
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_HOSTNAME, "co.metrc.com")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_USERNAME, "user")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_PASSWORD, "pass")
    mock_set_key.assert_any_call(cli.DEFAULT_ENV_PATH, EnvKeys.METRC_EMAIL, "test@example.com")


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_with_email(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["co.metrc.com", "user", "pass", "test@example.com"]
    result = cli.prompt_for_credentials_or_error()
    assert result == {
        "hostname": "co.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": "test@example.com",
    }
    mock_offer.assert_not_called()


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_with_stored_email(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["co.metrc.com", "user", "pass"]
    result = cli.prompt_for_credentials_or_error(email="stored@example.com")
    assert result == {
        "hostname": "co.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": "stored@example.com",
    }
    mock_offer.assert_not_called()


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_invalid_email_raises(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["co.metrc.com", "user", "pass", "invalid-email"]
    with pytest.raises(AuthenticationError, match="Invalid email address"):
        cli.prompt_for_credentials_or_error()
    mock_offer.assert_not_called()


@patch("typer.prompt")
@patch("t3api_utils.cli.utils.offer_to_save_credentials")
def test_prompt_for_credentials_no_email_for_non_whitelisted_hostname(mock_offer, mock_prompt):
    mock_prompt.side_effect = ["mo.metrc.com", "user", "pass"]
    result = cli.prompt_for_credentials_or_error()
    assert result == {
        "hostname": "mo.metrc.com",
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": None,
    }
    mock_offer.assert_not_called()


@patch.dict(os.environ, {
    EnvKeys.METRC_HOSTNAME.value: "mo.metrc.com",
    EnvKeys.METRC_USERNAME.value: "user",
    EnvKeys.METRC_PASSWORD.value: "pass",
})
@patch("typer.confirm", return_value=False)
@patch("t3api_utils.cli.utils.set_key")
def test_offer_to_save_credentials_email_differs_only_for_whitelisted_hostname(mock_set_key, mock_confirm):
    """Test that email differences are only checked for whitelisted hostnames."""
    # For non-whitelisted hostname, email differences should be ignored
    credentials: T3Credentials = {
        "hostname": "mo.metrc.com",  # Not in CREDENTIAL_EMAIL_WHITELIST
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": "different@example.com",  # Different from stored (empty), but should be ignored
    }
    cli.offer_to_save_credentials(credentials=credentials)
    # Should not prompt for update since email differences are ignored for non-whitelisted hostnames
    mock_confirm.assert_not_called()


@patch.dict(os.environ, {
    EnvKeys.METRC_HOSTNAME.value: "co.metrc.com",
    EnvKeys.METRC_USERNAME.value: "user",
    EnvKeys.METRC_PASSWORD.value: "pass",
})
@patch("typer.confirm", return_value=False)
@patch("t3api_utils.cli.utils.set_key")
def test_offer_to_save_credentials_email_differs_detected_for_whitelisted_hostname(mock_set_key, mock_confirm):
    """Test that email differences are detected for whitelisted hostnames."""
    # For whitelisted hostname, email differences should trigger update prompt
    credentials: T3Credentials = {
        "hostname": "co.metrc.com",  # In CREDENTIAL_EMAIL_WHITELIST
        "username": "user",
        "password": "pass",
        "otp": None,
        "email": "different@example.com",  # Different from stored (empty), should trigger update
    }
    cli.offer_to_save_credentials(credentials=credentials)
    # Should prompt for update since email differs and hostname requires email
    mock_confirm.assert_called_once()


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
