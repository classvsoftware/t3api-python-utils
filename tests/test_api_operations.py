"""Tests for T3 API operations."""
from unittest.mock import patch

import pytest

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.operations import (get_collection, get_collection_async,
                                        send_api_request, send_api_request_async)
from t3api_utils.http.utils import T3HTTPError


class TestSyncOperations:
    """Test synchronous API operations."""

    @patch('t3api_utils.http.utils.request_json')
    def test_get_collection_success(self, mock_request):
        """Test successful collection retrieval."""
        mock_response = {
            "data": [
                {
                    "id": "123",
                    "licenseNumber": "LIC-001",
                    "tag": "TAG-001"
                }
            ],
            "total": 1,
            "page": 1,
            "pageSize": 100
        }
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = get_collection(client, "/v2/packages/active", license_number="LIC-001")

        # Verify the request
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "GET"
        assert call_args[1]["url"] == "/v2/packages/active"
        expected_params = {
            "licenseNumber": "LIC-001",
            "page": 1,
            "pageSize": 100,
            "strictPagination": False,
            "filterLogic": "and"
        }
        assert call_args[1]["params"] == expected_params

        # Verify the response
        assert isinstance(result, dict)
        assert len(result["data"]) == 1
        assert result["data"][0]["licenseNumber"] == "LIC-001"

    @patch('t3api_utils.http.utils.request_json')
    def test_get_data_with_params(self, mock_request):
        """Test get_data with custom parameters."""
        mock_response = {"data": [], "total": 0, "page": 2, "pageSize": 50}
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = send_api_request(
            client,
            "/v2/licenses",
            params={
                "page": 2,
                "pageSize": 50,
                "state": "CA",
                "active_only": True
            }
        )

        # Verify the request parameters
        call_args = mock_request.call_args
        expected_params = {
            "page": 2,
            "pageSize": 50,
            "state": "CA",
            "active_only": True
        }
        assert call_args[1]["params"] == expected_params

    def test_send_api_request_not_authenticated(self):
        """Test send_api_request without authentication."""
        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            send_api_request(client, "/v2/licenses")

        assert "not authenticated" in str(exc_info.value)

    def test_get_collection_not_authenticated(self):
        """Test collection retrieval without authentication."""
        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            get_collection(client, "/v2/packages/active", license_number="LIC-001")

        assert "not authenticated" in str(exc_info.value)

    @patch('t3api_utils.http.utils.request_json')
    def test_get_packages_success(self, mock_request):
        """Test successful packages retrieval."""
        mock_response = {
            "data": [
                {
                    "id": "pkg-123",
                    "licenseNumber": "LIC-001",
                    "tag": "TAG-001"
                }
            ],
            "total": 1,
            "page": 1,
            "pageSize": 100
        }
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = get_collection(client, "/v2/packages/active", license_number="LIC-001")

        # Verify the request
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "GET"
        assert call_args[1]["url"] == "/v2/packages/active"
        expected_params = {
            "licenseNumber": "LIC-001",
            "page": 1,
            "pageSize": 100,
            "strictPagination": False,
            "filterLogic": "and"
        }
        assert call_args[1]["params"] == expected_params

        # Verify the response
        assert isinstance(result, dict)
        assert len(result["data"]) == 1
        assert result["data"][0]["licenseNumber"] == "LIC-001"

    def test_get_packages_not_authenticated(self):
        """Test packages retrieval without authentication."""
        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            get_collection(client, "/v2/packages/active", license_number="LIC-001")

        assert "not authenticated" in str(exc_info.value)

    @patch('t3api_utils.http.utils.request_json')
    def test_get_packages_api_error(self, mock_request):
        """Test packages retrieval with API error."""
        mock_request.side_effect = T3HTTPError("API Error")

        client = T3APIClient()
        client.set_access_token("test_token")

        with pytest.raises(T3HTTPError) as exc_info:
            get_collection(client, "/v2/packages/active", license_number="LIC-001")

        assert "Failed to get collection" in str(exc_info.value)


class TestAsyncOperations:
    """Test asynchronous API operations."""

    @pytest.mark.asyncio
    @patch('t3api_utils.api.operations.arequest_json')
    async def test_send_api_request_async_success(self, mock_request):
        """Test successful async send_api_request."""
        mock_response = {
            "data": [
                {
                    "id": "123",
                    "licenseNumber": "LIC-001",
                    "licenseName": "Test Company"
                }
            ],
            "total": 1,
            "page": 1,
            "pageSize": 100
        }
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = await send_api_request_async(client, "/v2/licenses")

        # Verify the request
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "GET"
        assert call_args[1]["url"] == "/v2/licenses"

        # Verify the response
        assert isinstance(result, dict)
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_send_api_request_async_not_authenticated(self):
        """Test async send_api_request without authentication."""
        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            await send_api_request_async(client, "/v2/licenses")

        assert "not authenticated" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_collection_async_not_authenticated(self):
        """Test async collection retrieval without authentication."""
        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            await get_collection_async(client, "/v2/packages/active", license_number="LIC-001")

        assert "not authenticated" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('t3api_utils.api.operations.arequest_json')
    async def test_get_packages_success(self, mock_request):
        """Test successful async packages retrieval."""
        mock_response = {
            "data": [
                {
                    "id": "pkg-123",
                    "licenseNumber": "LIC-001",
                    "tag": "TAG-001"
                }
            ],
            "total": 1,
            "page": 1,
            "pageSize": 100
        }
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = await get_collection_async(client, "/v2/packages/active", license_number="LIC-001")

        # Verify the request
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "GET"
        assert call_args[1]["url"] == "/v2/packages/active"

        # Verify the response
        assert isinstance(result, dict)
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_get_packages_not_authenticated(self):
        """Test async packages retrieval without authentication."""
        client = T3APIClient()

        with pytest.raises(T3HTTPError) as exc_info:
            await get_collection_async(client, "/v2/packages/active", license_number="LIC-001")

        assert "not authenticated" in str(exc_info.value)
        assert "not authenticated" in str(exc_info.value)