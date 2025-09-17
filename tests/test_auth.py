"""Tests for authentication utilities using httpx-based implementation."""
from unittest.mock import MagicMock, patch

import pytest

from t3api_utils.auth.utils import create_credentials_authenticated_client_or_error
from t3api_utils.api.client import T3APIClient
from t3api_utils.exceptions import AuthenticationError


def test_successful_authentication():
    """Test successful authentication using httpx-based implementation."""
    with patch('t3api_utils.auth.utils._httpx_auth_client') as mock_httpx_auth:
        mock_client = MagicMock(spec=T3APIClient)
        mock_httpx_auth.return_value = mock_client

        result = create_credentials_authenticated_client_or_error(
            host="https://api.test.com",
            hostname="ca.metrc.com",
            username="user",
            password="pass",
            otp="654321",
        )

        assert result == mock_client
        mock_httpx_auth.assert_called_once_with(
            hostname="ca.metrc.com",
            username="user",
            password="pass",
            host="https://api.test.com",
            otp="654321",
            email=None
        )


def test_authentication_error():
    """Test that authentication errors are properly propagated."""
    with patch('t3api_utils.auth.utils._httpx_auth_client') as mock_httpx_auth:
        mock_httpx_auth.side_effect = AuthenticationError("Invalid credentials")

        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            create_credentials_authenticated_client_or_error(
                hostname="ca.metrc.com",
                username="baduser",
                password="badpass",
            )


