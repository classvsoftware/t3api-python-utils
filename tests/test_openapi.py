"""Unit and integration tests for OpenAPI functionality."""

import json
from unittest.mock import Mock, patch
import pytest
import httpx

from t3api_utils.openapi.spec_fetcher import (
    fetch_openapi_spec,
    parse_collection_endpoints,
    get_collection_endpoints,
    _determine_category,
    _create_display_name,
)


class TestOpenAPISpecFetcher:
    """Unit tests for OpenAPI spec fetching."""

    @patch("t3api_utils.openapi.spec_fetcher.httpx.Client")
    def test_fetch_openapi_spec_success(self, mock_client_class):
        """Test successful OpenAPI spec fetch."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {"openapi": "3.0.0", "paths": {}}
        mock_response.raise_for_status.return_value = None

        # Mock client
        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        result = fetch_openapi_spec()

        assert result == {"openapi": "3.0.0", "paths": {}}
        mock_client.get.assert_called_once_with("https://api.trackandtrace.tools/v2/spec/openapi.json")

    @patch("t3api_utils.openapi.spec_fetcher.httpx.Client")
    @patch("t3api_utils.openapi.spec_fetcher.sys.exit")
    def test_fetch_openapi_spec_http_error(self, mock_exit, mock_client_class):
        """Test OpenAPI spec fetch with HTTP error."""
        # Mock client that raises HTTP error
        mock_client = Mock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        mock_client_class.return_value.__enter__.return_value = mock_client

        fetch_openapi_spec()

        mock_exit.assert_called_once_with(1)

    @patch("t3api_utils.openapi.spec_fetcher.httpx.Client")
    @patch("t3api_utils.openapi.spec_fetcher.sys.exit")
    def test_fetch_openapi_spec_json_error(self, mock_exit, mock_client_class):
        """Test OpenAPI spec fetch with JSON parsing error."""
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status.return_value = None

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        fetch_openapi_spec()

        mock_exit.assert_called_once_with(1)


class TestCollectionEndpointParser:
    """Unit tests for collection endpoint parsing."""

    def test_parse_collection_endpoints_success(self):
        """Test parsing collection endpoints from spec."""
        spec = {
            "paths": {
                "/v2/packages/active": {
                    "get": {
                        "tags": ["Collection", "Packages"],
                        "summary": "Get Active Packages",
                        "description": "Retrieve all active packages"
                    }
                },
                "/v2/licenses": {
                    "get": {
                        "tags": ["Collection", "Licenses"],
                        "summary": "Get Licenses"
                    }
                },
                "/v2/other": {
                    "get": {
                        "tags": ["NotCollection"],
                        "summary": "Other Endpoint"
                    }
                }
            }
        }

        endpoints = parse_collection_endpoints(spec)

        assert len(endpoints) == 2

        # Check first endpoint
        packages_endpoint = next(e for e in endpoints if "packages" in e["path"])
        assert packages_endpoint["path"] == "/v2/packages/active"
        assert packages_endpoint["method"] == "GET"
        assert packages_endpoint["name"] == "Get Active Packages"
        assert packages_endpoint["category"] == "Packages"
        assert packages_endpoint["description"] == "Retrieve all active packages"

        # Check second endpoint
        licenses_endpoint = next(e for e in endpoints if "licenses" in e["path"])
        assert licenses_endpoint["path"] == "/v2/licenses"
        assert licenses_endpoint["method"] == "GET"
        assert licenses_endpoint["name"] == "Get Licenses"
        assert licenses_endpoint["category"] == "Licenses"

    @patch("t3api_utils.openapi.spec_fetcher.sys.exit")
    def test_parse_collection_endpoints_none_found(self, mock_exit):
        """Test parsing when no collection endpoints are found."""
        spec = {
            "paths": {
                "/v2/other": {
                    "get": {
                        "tags": ["NotCollection"],
                        "summary": "Other Endpoint"
                    }
                }
            }
        }

        parse_collection_endpoints(spec)

        mock_exit.assert_called_once_with(1)

    def test_parse_collection_endpoints_empty_spec(self):
        """Test parsing with empty spec."""
        with patch("t3api_utils.openapi.spec_fetcher.sys.exit") as mock_exit:
            parse_collection_endpoints({})
            mock_exit.assert_called_once_with(1)


class TestHelperFunctions:
    """Unit tests for helper functions."""

    def test_determine_category_from_tags(self):
        """Test category determination from tags."""
        assert _determine_category("/v2/packages", ["Collection", "Packages"]) == "Packages"
        assert _determine_category("/v2/licenses", ["Collection", "Licenses"]) == "Licenses"

    def test_determine_category_from_path(self):
        """Test category determination from path when no other tags."""
        assert _determine_category("/v2/packages/active", ["Collection"]) == "Packages"
        assert _determine_category("/v2/licenses", ["Collection"]) == "Licenses"

    def test_determine_category_fallback(self):
        """Test category determination fallback."""
        assert _determine_category("/", ["Collection"]) == "General"
        assert _determine_category("/v2", ["Collection"]) == "General"

    def test_create_display_name_from_summary(self):
        """Test display name creation from summary."""
        assert _create_display_name("Get Active Packages", "/v2/packages/active") == "Get Active Packages"

    def test_create_display_name_from_path(self):
        """Test display name creation from path."""
        assert _create_display_name("", "/v2/packages/active") == "Packages Active"
        assert _create_display_name("", "/v2/lab-tests") == "Lab Tests"

    def test_create_display_name_fallback(self):
        """Test display name fallback to path."""
        assert _create_display_name("", "/") == "/"
        assert _create_display_name("", "/v2") == "/v2"


class TestIntegrationGetCollectionEndpoints:
    """Integration tests for the main function."""

    @patch("t3api_utils.openapi.spec_fetcher.fetch_openapi_spec")
    def test_get_collection_endpoints_integration(self, mock_fetch):
        """Test the full integration of fetching and parsing."""
        mock_fetch.return_value = {
            "paths": {
                "/v2/packages/active": {
                    "get": {
                        "tags": ["Collection", "Packages"],
                        "summary": "Get Active Packages"
                    }
                }
            }
        }

        endpoints = get_collection_endpoints()

        assert len(endpoints) == 1
        assert endpoints[0]["path"] == "/v2/packages/active"
        assert endpoints[0]["name"] == "Get Active Packages"