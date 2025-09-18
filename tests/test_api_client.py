"""Tests for T3APIClient."""
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from t3api_utils.api.client import AsyncT3APIClient, T3APIClient
from t3api_utils.api.interfaces import AuthResponseData, MetrcCollectionResponse
from t3api_utils.http.utils import HTTPConfig, RetryPolicy, T3HTTPError


class TestT3APIClient:
    """Test T3APIClient synchronous operations."""

    def test_initialization(self):
        """Test client initialization."""
        client = T3APIClient()
        assert client._config is not None
        assert client._retry_policy is not None
        assert not client.is_authenticated
        assert client.access_token is None

    def test_initialization_with_config(self):
        """Test client initialization with custom config."""
        config = HTTPConfig(host="https://custom.api.com")
        retry_policy = RetryPolicy(max_attempts=5)
        headers = {"Custom-Header": "value"}

        client = T3APIClient(
            config=config,
            retry_policy=retry_policy,
            headers=headers
        )

        assert client._config == config
        assert client._retry_policy == retry_policy
        assert client._extra_headers == headers

    def test_context_manager(self):
        """Test context manager functionality."""
        with patch.object(httpx.Client, 'close') as mock_close:
            with T3APIClient() as client:
                assert isinstance(client, T3APIClient)
            mock_close.assert_called_once()

    def test_set_access_token(self):
        """Test setting access token."""
        client = T3APIClient()
        token = "test_access_token"

        client.set_access_token(token)

        assert client.is_authenticated
        assert client.access_token == token
        assert client._client.headers["Authorization"] == f"Bearer {token}"

    def test_clear_access_token(self):
        """Test clearing access token."""
        client = T3APIClient()
        client.set_access_token("test_token")

        client.clear_access_token()

        assert not client.is_authenticated
        assert client.access_token is None
        assert "Authorization" not in client._client.headers

    @patch('t3api_utils.api.client.request_json')
    def test_authenticate_with_credentials_success(self, mock_request):
        """Test successful authentication."""
        # Mock the API response
        mock_response = {
            "accessToken": "test_access_token",
        }
        mock_request.return_value = mock_response

        client = T3APIClient()
        result = client.authenticate_with_credentials(
            hostname="test.example.com",
            username="testuser",
            password="testpass",
            otp="123456",
            email="test@example.com"
        )

        # Verify the request was made correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["url"] == "/v2/auth/credentials"
        assert call_args[1]["json_body"] == {
            "hostname": "test.example.com",
            "username": "testuser",
            "password": "testpass",
            "otp": "123456",
            "email": "test@example.com"
        }

        # Verify the response
        assert isinstance(result, dict)
        assert result["accessToken"] == "test_access_token"

        # Verify client state
        assert client.is_authenticated
        assert client.access_token == "test_access_token"

    @patch('t3api_utils.api.client.request_json')
    def test_authenticate_with_credentials_minimal(self, mock_request):
        """Test authentication with minimal parameters."""
        mock_response = {
            "accessToken": "test_access_token"
        }
        mock_request.return_value = mock_response

        client = T3APIClient()
        result = client.authenticate_with_credentials(
            hostname="test.example.com",
            username="testuser",
            password="testpass"
        )

        # Verify the request payload
        call_args = mock_request.call_args
        assert call_args[1]["json_body"] == {
            "hostname": "test.example.com",
            "username": "testuser",
            "password": "testpass"
        }

        # Verify response handling
        assert result["accessToken"] == "test_access_token"

    @patch('t3api_utils.api.client.request_json')
    def test_authenticate_with_credentials_failure(self, mock_request):
        """Test authentication failure."""
        mock_request.side_effect = T3HTTPError("Authentication failed")

        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            client.authenticate_with_credentials(
                hostname="test.example.com",
                username="testuser",
                password="wrongpass"
            )

        assert "Authentication failed" in str(exc_info.value)
        assert not client.is_authenticated



class TestAsyncT3APIClient:
    """Test AsyncT3APIClient asynchronous operations."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test async client initialization."""
        client = AsyncT3APIClient()
        assert client._config is not None
        assert client._retry_policy is not None
        assert not client.is_authenticated
        assert client.access_token is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager functionality."""
        with patch.object(httpx.AsyncClient, 'aclose') as mock_close:
            async with AsyncT3APIClient() as client:
                assert isinstance(client, AsyncT3APIClient)
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_access_token(self):
        """Test setting access token on async client."""
        client = AsyncT3APIClient()
        token = "test_access_token"

        client.set_access_token(token)

        assert client.is_authenticated
        assert client.access_token == token
        assert client._client.headers["Authorization"] == f"Bearer {token}"

    @pytest.mark.asyncio
    @patch('t3api_utils.api.client.arequest_json')
    async def test_authenticate_with_credentials_success(self, mock_request):
        """Test successful async authentication."""
        mock_response = {
            "accessToken": "test_access_token",
        }
        mock_request.return_value = mock_response

        client = AsyncT3APIClient()
        result = await client.authenticate_with_credentials(
            hostname="test.example.com",
            username="testuser",
            password="testpass"
        )

        # Verify the request was made correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["url"] == "/v2/auth/credentials"

        # Verify the response
        assert isinstance(result, dict)
        assert result["accessToken"] == "test_access_token"
        assert client.is_authenticated

