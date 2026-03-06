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

    @patch('t3api_utils.http.utils.request_json')
    def test_send_api_request_with_files(self, mock_request):
        """Test send_api_request with multipart file upload."""
        mock_request.return_value = {"uploaded": True}

        client = T3APIClient()
        client.set_access_token("test_token")

        test_files = {"file": ("test.png", b"\x89PNG", "image/png")}
        result = send_api_request(
            client,
            "/v2/items/images/file",
            method="POST",
            params={"licenseNumber": "LIC-001", "fileType": "ItemProductImage", "submit": True},
            files=test_files,
        )

        assert result == {"uploaded": True}
        call_args = mock_request.call_args
        assert call_args[1]["files"] == test_files
        assert call_args[1]["json_body"] is None
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["params"]["licenseNumber"] == "LIC-001"

    def test_send_api_request_files_and_json_body_mutually_exclusive(self):
        """Test that providing both json_body and files raises ValueError."""
        client = T3APIClient()
        client.set_access_token("test_token")

        with pytest.raises(ValueError, match="mutually exclusive"):
            send_api_request(
                client,
                "/v2/test",
                method="POST",
                json_body={"data": "test"},
                files={"file": ("test.png", b"\x89PNG", "image/png")},
            )

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

    @patch('t3api_utils.http.utils.request_bytes')
    def test_send_api_request_response_type_bytes(self, mock_request):
        """Test send_api_request with response_type='bytes'."""
        mock_request.return_value = b"\x89PNG\r\n\x1a\n"

        client = T3APIClient()
        client.set_access_token("test_token")

        result = send_api_request(client, "/v2/reports/manifest", response_type="bytes")

        assert result == b"\x89PNG\r\n\x1a\n"
        assert isinstance(result, bytes)
        mock_request.assert_called_once()

    @patch('t3api_utils.http.utils.request_text')
    def test_send_api_request_response_type_text(self, mock_request):
        """Test send_api_request with response_type='text'."""
        mock_request.return_value = "col1,col2\na,b\n"

        client = T3APIClient()
        client.set_access_token("test_token")

        result = send_api_request(client, "/v2/exports/packages.csv", response_type="text")

        assert result == "col1,col2\na,b\n"
        assert isinstance(result, str)
        mock_request.assert_called_once()

    @patch('t3api_utils.http.utils.request_raw')
    def test_send_api_request_response_type_response(self, mock_request):
        """Test send_api_request with response_type='response'."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = send_api_request(client, "/v2/reports/summary", response_type="response")

        assert result is mock_response
        assert result.headers["content-type"] == "application/pdf"

    @patch('t3api_utils.http.utils.request_json')
    def test_send_api_request_default_response_type(self, mock_request):
        """Test send_api_request defaults to response_type='json'."""
        mock_request.return_value = {"key": "value"}

        client = T3APIClient()
        client.set_access_token("test_token")

        result = send_api_request(client, "/v2/licenses")

        assert result == {"key": "value"}
        mock_request.assert_called_once()


class TestAsyncOperations:
    """Test asynchronous API operations."""

    @pytest.mark.asyncio
    @patch('t3api_utils.http.utils.arequest_json')
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
    @patch('t3api_utils.http.utils.arequest_json')
    async def test_send_api_request_async_with_files(self, mock_request):
        """Test async send_api_request with multipart file upload."""
        mock_request.return_value = {"uploaded": True}

        client = T3APIClient()
        client.set_access_token("test_token")

        test_files = {"file": ("test.png", b"\x89PNG", "image/png")}
        result = await send_api_request_async(
            client,
            "/v2/items/images/file",
            method="POST",
            params={"licenseNumber": "LIC-001"},
            files=test_files,
        )

        assert result == {"uploaded": True}
        call_args = mock_request.call_args
        assert call_args[1]["files"] == test_files
        assert call_args[1]["json_body"] is None

    @pytest.mark.asyncio
    async def test_send_api_request_async_files_and_json_body_mutually_exclusive(self):
        """Test that providing both json_body and files raises ValueError (async)."""
        client = T3APIClient()
        client.set_access_token("test_token")

        with pytest.raises(ValueError, match="mutually exclusive"):
            await send_api_request_async(
                client,
                "/v2/test",
                method="POST",
                json_body={"data": "test"},
                files={"file": ("test.png", b"\x89PNG", "image/png")},
            )

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
    @patch('t3api_utils.http.utils.arequest_json')
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

    @pytest.mark.asyncio
    @patch('t3api_utils.http.utils.arequest_bytes')
    async def test_send_api_request_async_response_type_bytes(self, mock_request):
        """Test async send_api_request with response_type='bytes'."""
        mock_request.return_value = b"%PDF-1.4"

        client = T3APIClient()
        client.set_access_token("test_token")

        result = await send_api_request_async(client, "/v2/reports/manifest", response_type="bytes")

        assert result == b"%PDF-1.4"
        assert isinstance(result, bytes)
        mock_request.assert_called_once()

    @pytest.mark.asyncio
    @patch('t3api_utils.http.utils.arequest_text')
    async def test_send_api_request_async_response_type_text(self, mock_request):
        """Test async send_api_request with response_type='text'."""
        mock_request.return_value = "<html><body>Report</body></html>"

        client = T3APIClient()
        client.set_access_token("test_token")

        result = await send_api_request_async(client, "/v2/reports/summary", response_type="text")

        assert result == "<html><body>Report</body></html>"
        assert isinstance(result, str)
        mock_request.assert_called_once()

    @pytest.mark.asyncio
    @patch('t3api_utils.http.utils.arequest_raw')
    async def test_send_api_request_async_response_type_response(self, mock_request):
        """Test async send_api_request with response_type='response'."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/csv"}
        mock_request.return_value = mock_response

        client = T3APIClient()
        client.set_access_token("test_token")

        result = await send_api_request_async(client, "/v2/exports/data.csv", response_type="response")

        assert result is mock_response

    @pytest.mark.asyncio
    @patch('t3api_utils.http.utils.arequest_json')
    async def test_send_api_request_async_default_response_type(self, mock_request):
        """Test async send_api_request defaults to response_type='json'."""
        mock_request.return_value = {"licenses": []}

        client = T3APIClient()
        client.set_access_token("test_token")

        result = await send_api_request_async(client, "/v2/licenses")

        assert result == {"licenses": []}
        mock_request.assert_called_once()