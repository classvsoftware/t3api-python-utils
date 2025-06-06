from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from t3api_utils.cli import app
from t3api_utils.decorators import OTP_WHITELIST, cli_options

runner = CliRunner()


# Register a new CLI function dynamically for testing purposes
def setup_dummy_command():
    @cli_options
    def dummy_func(host, hostname, username, password, otp):
        print(
            f"[test-output] host={host}, hostname={hostname}, username={username}, password={password}, otp={otp}"
        )

    app.command(name="dummy")(dummy_func)


@pytest.fixture(autouse=True)
def setup_test_command():
    setup_dummy_command()


@patch("typer.prompt")
def test_all_values_prompted(mock_prompt):
    mock_prompt.side_effect = [
        "mo.metrc.com",  # hostname
        "testuser",  # username
        "secretpw",  # password
        "654321",  # otp
    ]

    result = runner.invoke(app, ["dummy"])
    assert result.exit_code == 0
    assert "host=https://api.trackandtrace.tools" in result.stdout
    assert "hostname=mo.metrc.com" in result.stdout
    assert "username=testuser" in result.stdout
    assert "password=secretpw" in result.stdout
    assert "otp=654321" in result.stdout


@patch("typer.prompt")
def test_no_otp_if_hostname_not_whitelisted(mock_prompt):
    mock_prompt.side_effect = [
        "ca.metrc.com",  # hostname
        "user",  # username
        "pw",  # password
    ]

    result = runner.invoke(app, ["dummy"])
    assert result.exit_code == 0
    assert "hostname=ca.metrc.com" in result.stdout
    assert "otp=None" in result.stdout


@patch("typer.prompt")
def test_custom_host_passed_via_flag(mock_prompt):
    mock_prompt.side_effect = [
        "wa.metrc.com",  # hostname
        "user2",  # username
        "pw2",  # password
    ]

    result = runner.invoke(app, ["dummy", "--host", "https://custom.t3.local"])
    assert result.exit_code == 0
    assert "host=https://custom.t3.local" in result.stdout
    assert "hostname=wa.metrc.com" in result.stdout
    assert "username=user2" in result.stdout
