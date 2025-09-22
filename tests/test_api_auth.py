"""Tests for API authentication utilities."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t3api_utils.auth.utils import (
    authenticate_and_get_response, authenticate_and_get_token,
    create_credentials_authenticated_client_or_error)
from t3api_utils.api.interfaces import AuthResponseData
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.http.utils import HTTPConfig, T3HTTPError


class TestCreateCredentialsAuthenticatedClientOrError:
    """Test create_credentials_authenticated_client_or_error function."""

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_successful_authentication(self, mock_client_class):
        """Test successful authentication returns authenticated client."""
        # Mock the client instance and authentication response
        mock_client = MagicMock()
        mock_auth_response = {"accessToken": "test_token"}
        mock_client.authenticate_with_credentials = AsyncMock(return_value=mock_auth_response)
        mock_client_class.return_value = mock_client

        # Call the function
        result = create_credentials_authenticated_client_or_error(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            otp="123456",
            email="test@example.com"
        )

        # Verify client was created with correct config
        mock_client_class.assert_called_once()
        call_args = mock_client_class.call_args
        config = call_args[1]["config"]
        assert isinstance(config, HTTPConfig)
        assert config.host == "https://api.trackandtrace.tools"

        # Verify authentication was called correctly
        mock_client.authenticate_with_credentials.assert_called_once_with(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            otp="123456",
            email="test@example.com"
        )

        # Verify the client is returned
        assert result == mock_client

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_custom_host(self, mock_client_class):
        """Test authentication with custom host."""
        mock_client = MagicMock()
        mock_auth_response = {"accessToken": "test_token"}
        mock_client.authenticate_with_credentials = AsyncMock(return_value=mock_auth_response)
        mock_client_class.return_value = mock_client

        result = create_credentials_authenticated_client_or_error(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            host="https://custom.api.com"
        )

        # Verify client was created with custom host
        call_args = mock_client_class.call_args
        config = call_args[1]["config"]
        assert config.host == "https://custom.api.com"

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_minimal_parameters(self, mock_client_class):
        """Test authentication with minimal required parameters."""
        mock_client = MagicMock()
        mock_auth_response = {"accessToken": "test_token"}
        mock_client.authenticate_with_credentials = AsyncMock(return_value=mock_auth_response)
        mock_client_class.return_value = mock_client

        result = create_credentials_authenticated_client_or_error(
            hostname="test.example.com",
            username="testuser",
            password="testpass"
        )

        # Verify authentication was called with None for optional params
        mock_client.authenticate_with_credentials.assert_called_once_with(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            otp=None,
            email=None
        )

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_t3http_error_handling(self, mock_client_class):
        """Test handling of T3HTTPError during authentication."""
        mock_client = MagicMock()
        mock_client.authenticate_with_credentials.side_effect = T3HTTPError("Auth failed")
        mock_client_class.return_value = mock_client

        with pytest.raises(AuthenticationError) as exc_info:
            create_credentials_authenticated_client_or_error(
                hostname="test.example.com",
                username="testuser",
                password="wrongpass"
            )

        assert "T3 API authentication failed" in str(exc_info.value)
        assert "Auth failed" in str(exc_info.value)

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_generic_error_handling(self, mock_client_class):
        """Test handling of generic exceptions during authentication."""
        mock_client_class.side_effect = ValueError("Some unexpected error")

        with pytest.raises(AuthenticationError) as exc_info:
            create_credentials_authenticated_client_or_error(
                hostname="test.example.com",
                username="testuser",
                password="testpass"
            )

        assert "Unexpected authentication error" in str(exc_info.value)
        assert "Some unexpected error" in str(exc_info.value)


class TestAuthenticateAndGetToken:
    """Test authenticate_and_get_token function."""

    @patch('t3api_utils.auth.utils.create_credentials_authenticated_client_or_error_async')
    def test_successful_token_retrieval(self, mock_create_client):
        """Test successful token retrieval."""
        # Mock the authenticated client
        mock_client = MagicMock()
        mock_client.access_token = "test_access_token"
        mock_client.close = AsyncMock()
        mock_create_client.return_value = mock_client

        result = authenticate_and_get_token(
            hostname="test.example.com",
            username="testuser",
            password="testpass"
        )

        # Verify the client creation was called correctly
        mock_create_client.assert_called_once_with(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            host=None,
            otp=None,
            email=None
        )

        # Verify the token is returned
        assert result == "test_access_token"

    @patch('t3api_utils.auth.utils.create_credentials_authenticated_client_or_error_async')
    def test_no_access_token_error(self, mock_create_client):
        """Test error when no access token is returned."""
        # Mock client with no access token
        mock_client = MagicMock()
        mock_client.access_token = None
        mock_client.close = AsyncMock()
        mock_create_client.return_value = mock_client

        with pytest.raises(AuthenticationError) as exc_info:
            authenticate_and_get_token(
                hostname="test.example.com",
                username="testuser",
                password="testpass"
            )

        assert "no access token was returned" in str(exc_info.value)

    @patch('t3api_utils.auth.utils.create_credentials_authenticated_client_or_error_async')
    def test_propagates_authentication_error(self, mock_create_client):
        """Test that AuthenticationError is propagated."""
        mock_create_client.side_effect = AuthenticationError("Auth failed")

        with pytest.raises(AuthenticationError) as exc_info:
            authenticate_and_get_token(
                hostname="test.example.com",
                username="testuser",
                password="testpass"
            )

        assert "Auth failed" in str(exc_info.value)


class TestAuthenticateAndGetResponse:
    """Test authenticate_and_get_response function."""

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_successful_response_retrieval(self, mock_client_class):
        """Test successful authentication response retrieval."""
        # Mock the client and authentication response
        mock_client = MagicMock()
        mock_auth_response = {
            "accessToken": "test_token",
        }
        mock_client.authenticate_with_credentials = AsyncMock(return_value=mock_auth_response)

        # Mock context manager
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = authenticate_and_get_response(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            otp="123456"
        )

        # Verify client was created with correct config
        mock_client_class.assert_called_once()
        call_args = mock_client_class.call_args
        config = call_args[1]["config"]
        assert config.host == "https://api.trackandtrace.tools"

        # Verify authentication was called
        mock_client.authenticate_with_credentials.assert_called_once_with(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            otp="123456",
            email=None
        )

        # Verify async context manager was used
        mock_client.__aenter__.assert_called_once()
        mock_client.__aexit__.assert_called_once()

        # Verify the response is returned
        assert result == mock_auth_response
        assert result["accessToken"] == "test_token"

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_custom_host_response(self, mock_client_class):
        """Test authentication response with custom host."""
        mock_client = MagicMock()
        mock_auth_response = {"accessToken": "test_token"}
        mock_client.authenticate_with_credentials = AsyncMock(return_value=mock_auth_response)

        # Mock async context manager
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = authenticate_and_get_response(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            host="https://staging.api.com"
        )

        # Verify client was created with custom host
        call_args = mock_client_class.call_args
        config = call_args[1]["config"]
        assert config.host == "https://staging.api.com"

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_t3http_error_in_response(self, mock_client_class):
        """Test T3HTTPError handling in response function."""
        mock_client = MagicMock()
        mock_client.authenticate_with_credentials = AsyncMock(side_effect=T3HTTPError("Auth error"))

        # Mock context manager
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with pytest.raises(AuthenticationError) as exc_info:
            authenticate_and_get_response(
                hostname="test.example.com",
                username="testuser",
                password="wrongpass"
            )

        assert "T3 API authentication failed" in str(exc_info.value)
        assert "Auth error" in str(exc_info.value)

    @patch('t3api_utils.auth.utils.T3APIClient')
    def test_generic_error_in_response(self, mock_client_class):
        """Test generic exception handling in response function."""
        mock_client_class.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(AuthenticationError) as exc_info:
            authenticate_and_get_response(
                hostname="test.example.com",
                username="testuser",
                password="testpass"
            )

        assert "Unexpected authentication error" in str(exc_info.value)
        assert "Unexpected error" in str(exc_info.value)