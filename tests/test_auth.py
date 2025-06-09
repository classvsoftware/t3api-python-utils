from unittest.mock import MagicMock, patch

import pytest

from t3api_utils.auth.utils import \
    create_credentials_authenticated_client_or_error
from t3api_utils.exceptions import AuthenticationError


@patch("t3api_utils.auth.utils.AuthenticationApi")
@patch("t3api_utils.auth.utils.ApiClient")
@patch("t3api_utils.auth.utils.Configuration")
def test_successful_authentication(mock_config, mock_api_client, mock_auth_api):
    mock_config_instance = MagicMock()
    mock_config.return_value = mock_config_instance

    mock_client_instance = MagicMock()
    mock_api_client.return_value = mock_client_instance

    mock_auth_instance = MagicMock()
    mock_response = MagicMock(access_token="abc123")
    mock_auth_instance.v2_auth_credentials_post.return_value = mock_response
    mock_auth_api.return_value = mock_auth_instance

    client = create_credentials_authenticated_client_or_error(
        host="https://api.test.com",
        hostname="ca.metrc.com",
        username="user",
        password="pass",
        otp="654321",
    )

    assert client == mock_client_instance
    assert mock_config_instance.access_token == "abc123"


@patch("t3api_utils.auth.utils.AuthenticationApi")
@patch("t3api_utils.auth.utils.ApiClient")
@patch("t3api_utils.auth.utils.Configuration")
def test_authentication_api_exception(mock_config, mock_api_client, mock_auth_api):
    mock_auth_instance = MagicMock()
    mock_auth_api.return_value = mock_auth_instance

    from t3api.exceptions import ApiException

    mock_auth_instance.v2_auth_credentials_post.side_effect = ApiException(
        body="invalid credentials"
    )

    with pytest.raises(
        AuthenticationError, match="T3 API authentication failed: invalid credentials"
    ):
        create_credentials_authenticated_client_or_error(
            host="https://api.test.com",
            hostname="ca.metrc.com",
            username="baduser",
            password="badpass",
        )


@patch("t3api_utils.auth.utils.AuthenticationApi")
@patch("t3api_utils.auth.utils.ApiClient")
@patch("t3api_utils.auth.utils.Configuration")
def test_unexpected_exception(mock_config, mock_api_client, mock_auth_api):
    mock_auth_instance = MagicMock()
    mock_auth_api.return_value = mock_auth_instance

    mock_auth_instance.v2_auth_credentials_post.side_effect = ValueError("boom")

    with pytest.raises(
        AuthenticationError, match="Unexpected authentication error: boom"
    ):
        create_credentials_authenticated_client_or_error(
            host="https://api.test.com",
            hostname="ca.metrc.com",
            username="x",
            password="y",
        )
