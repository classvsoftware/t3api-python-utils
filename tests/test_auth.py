"""Tests for authentication utilities using httpx-based implementation."""
from unittest.mock import MagicMock, patch

import pytest

from t3api_utils.api.client import T3APIClient
from t3api_utils.auth.utils import create_jwt_authenticated_client
from t3api_utils.http.utils import HTTPConfig, RetryPolicy


class TestCreateJwtAuthenticatedClient:
    """Test JWT token authentication."""

    def test_successful_jwt_authentication_default_config(self):
        """Test successful JWT authentication with default configuration."""
        test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"

        with patch('t3api_utils.auth.utils.T3APIClient') as mock_client_class:
            mock_client = MagicMock(spec=T3APIClient)
            mock_client_class.return_value = mock_client

            result = create_jwt_authenticated_client(jwt_token=test_token)

            assert result == mock_client

            # Verify T3APIClient was called with default HTTPConfig
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs['retry_policy'] is None
            assert call_kwargs['logging_hooks'] is None
            assert call_kwargs['headers'] is None

            # Verify HTTPConfig was created with default host
            config = call_kwargs['config']
            assert config.host == "https://api.trackandtrace.tools"

            # Verify set_access_token was called
            mock_client.set_access_token.assert_called_once_with(test_token)

    def test_jwt_authentication_with_custom_host(self):
        """Test JWT authentication with custom host."""
        test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
        custom_host = "https://api.staging.trackandtrace.tools"

        with patch('t3api_utils.auth.utils.T3APIClient') as mock_client_class:
            mock_client = MagicMock(spec=T3APIClient)
            mock_client_class.return_value = mock_client

            result = create_jwt_authenticated_client(jwt_token=test_token, host=custom_host)

            assert result == mock_client

            # Verify HTTPConfig was created with custom host
            call_kwargs = mock_client_class.call_args[1]
            config = call_kwargs['config']
            assert config.host == custom_host

            mock_client.set_access_token.assert_called_once_with(test_token)

    def test_jwt_authentication_with_custom_config(self):
        """Test JWT authentication with custom HTTPConfig."""
        test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
        custom_config = HTTPConfig(
            host="https://api.custom.com",
            timeout=30.0
        )

        with patch('t3api_utils.auth.utils.T3APIClient') as mock_client_class:
            mock_client = MagicMock(spec=T3APIClient)
            mock_client_class.return_value = mock_client

            result = create_jwt_authenticated_client(jwt_token=test_token, config=custom_config)

            assert result == mock_client

            # Should use the provided config as-is when no host is explicitly specified
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs['config'] == custom_config

            mock_client.set_access_token.assert_called_once_with(test_token)

    def test_jwt_authentication_with_config_host_mismatch(self):
        """Test JWT authentication when config host doesn't match specified host."""
        test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
        original_config = HTTPConfig(
            host="https://api.original.com",
            timeout=30.0
        )
        specified_host = "https://api.different.com"

        with patch('t3api_utils.auth.utils.T3APIClient') as mock_client_class:
            mock_client = MagicMock(spec=T3APIClient)
            mock_client_class.return_value = mock_client

            result = create_jwt_authenticated_client(
                jwt_token=test_token,
                host=specified_host,
                config=original_config
            )

            assert result == mock_client

            # Should create new config with specified host but preserve other settings
            call_kwargs = mock_client_class.call_args[1]
            new_config = call_kwargs['config']
            assert new_config.host == specified_host
            assert new_config.timeout == original_config.timeout
            assert new_config.verify_ssl == original_config.verify_ssl
            assert new_config.base_headers == original_config.base_headers
            assert new_config.proxies == original_config.proxies

            mock_client.set_access_token.assert_called_once_with(test_token)

    def test_jwt_authentication_with_all_options(self):
        """Test JWT authentication with all optional parameters."""
        test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
        custom_config = HTTPConfig(host="https://api.custom.com")
        custom_retry = RetryPolicy(max_attempts=3)
        custom_headers = {"X-Custom": "header"}

        with patch('t3api_utils.auth.utils.T3APIClient') as mock_client_class:
            mock_client = MagicMock(spec=T3APIClient)
            mock_client_class.return_value = mock_client

            result = create_jwt_authenticated_client(
                jwt_token=test_token,
                config=custom_config,
                retry_policy=custom_retry,
                logging_hooks=None,
                headers=custom_headers
            )

            assert result == mock_client

            # Verify all parameters were passed through
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs['config'] == custom_config
            assert call_kwargs['retry_policy'] == custom_retry
            assert call_kwargs['logging_hooks'] is None
            assert call_kwargs['headers'] == custom_headers

            mock_client.set_access_token.assert_called_once_with(test_token)

    def test_jwt_authentication_strips_whitespace(self):
        """Test that JWT token whitespace is stripped."""
        test_token = "  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature  "
        expected_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"

        with patch('t3api_utils.auth.utils.T3APIClient') as mock_client_class:
            mock_client = MagicMock(spec=T3APIClient)
            mock_client_class.return_value = mock_client

            result = create_jwt_authenticated_client(jwt_token=test_token)

            assert result == mock_client
            mock_client.set_access_token.assert_called_once_with(expected_token)

    def test_jwt_authentication_empty_token_raises_error(self):
        """Test that empty JWT token raises ValueError."""
        with pytest.raises(ValueError, match="JWT token cannot be empty or None"):
            create_jwt_authenticated_client(jwt_token="")

    def test_jwt_authentication_none_token_raises_error(self):
        """Test that None JWT token raises ValueError."""
        with pytest.raises(ValueError, match="JWT token cannot be empty or None"):
            create_jwt_authenticated_client(jwt_token=None)  # type: ignore

    def test_jwt_authentication_whitespace_only_token_raises_error(self):
        """Test that whitespace-only JWT token raises ValueError."""
        with pytest.raises(ValueError, match="JWT token cannot be empty or None"):
            create_jwt_authenticated_client(jwt_token="   ")


