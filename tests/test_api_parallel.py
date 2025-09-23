"""Tests for parallel API utilities."""
import asyncio
import time
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t3api_utils.api.client import T3APIClient, T3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse
from t3api_utils.api.parallel import (RateLimiter, load_all_data_async,
                                      load_all_data_sync,
                                      parallel_load_collection_enhanced,
                                      parallel_load_paginated_async,
                                      parallel_load_paginated_sync)


class TestRateLimiter:
    """Test RateLimiter functionality."""

    def test_no_rate_limit(self):
        """Test rate limiter with no limit (0 or None)."""
        limiter = RateLimiter(0)

        start_time = time.time()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()
        end_time = time.time()

        # Should complete almost instantly
        assert end_time - start_time < 0.1

    def test_rate_limiting(self):
        """Test rate limiter with actual rate limiting."""
        limiter = RateLimiter(100)  # 100 requests per second = 0.01s interval

        start_time = time.time()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()
        end_time = time.time()

        # Should take at least 0.02 seconds (2 intervals)
        assert end_time - start_time >= 0.015

    @pytest.mark.asyncio
    async def test_async_no_rate_limit(self):
        """Test async rate limiter with no limit."""
        limiter = RateLimiter(0)

        start_time = time.time()
        await limiter.acquire_async()
        await limiter.acquire_async()
        await limiter.acquire_async()
        end_time = time.time()

        # Should complete almost instantly
        assert end_time - start_time < 0.1

    @pytest.mark.asyncio
    async def test_async_rate_limiting(self):
        """Test async rate limiter with actual rate limiting."""
        limiter = RateLimiter(100)  # 100 requests per second = 0.01s interval

        start_time = time.time()
        await limiter.acquire_async()
        await limiter.acquire_async()
        await limiter.acquire_async()
        end_time = time.time()

        # Should take at least 0.02 seconds (2 intervals)
        assert end_time - start_time >= 0.015


class TestParallelLoadPaginatedSync:
    """Test parallel_load_paginated_sync functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

        # Add required attributes for asyncio wrapper
        from t3api_utils.http.utils import HTTPConfig, RetryPolicy
        self.mock_client._config = HTTPConfig()
        self.mock_client._retry_policy = RetryPolicy()
        self.mock_client._logging_hooks = None
        self.mock_client._extra_headers = {}
        self.mock_client._access_token = "test_token"

    @patch('t3api_utils.api.parallel.get_collection_async')
    def test_single_page_response(self, mock_get_collection_async):
        """Test loading when there's only one page."""
        # Mock response with single page
        mock_response: MetrcCollectionResponse = {
            "data": [{
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            }],
            "total": 1,
            "page": 1,
            "pageSize": 10
        }

        mock_get_collection_async.return_value = mock_response

        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            path="/v2/licenses"
        )

        assert len(result) == 1
        assert result[0] == mock_response
        # Verify the async function was called (client will be different due to wrapper)
        mock_get_collection_async.assert_called_once()
        call_args = mock_get_collection_async.call_args
        assert call_args[0][1] == "/v2/licenses"  # endpoint
        assert call_args[1]["page"] == 1  # page parameter

    @patch('t3api_utils.api.parallel.get_collection_async')
    def test_multiple_pages_response(self, mock_get_collection_async):
        """Test loading when there are multiple pages."""
        def mock_method_side_effect(client, path, page=1, **kwargs):
            if page == 1:
                return {
                    "data": [{
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            }],
                    "total": 25,
                    "page": 1,
                    "pageSize": 10
                }
            elif page == 2:
                return {
                    "data": [{"id": "2", "licenseNumber": "LIC-002", "licenseName": "Company 2"}],
                    "total": 25,
                    "page": 2,
                    "pageSize": 10
                }
            elif page == 3:
                return {
                    "data": [{"id": "3", "licenseNumber": "LIC-003", "licenseName": "Company 3"}],
                    "total": 25,
                    "page": 3,
                    "pageSize": 10
                }

        mock_get_collection_async.side_effect = mock_method_side_effect

        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            path="/v2/licenses"
        )

        # Should return 3 pages total (25 items / 10 per page = 3 pages)
        assert len(result) == 3
        assert mock_get_collection_async.call_count == 3

    @patch('t3api_utils.api.parallel.get_collection_async')
    def test_rate_limiting_applied(self, mock_get_collection_async):
        """Test that rate limiting is properly applied."""
        mock_response: MetrcCollectionResponse = {
            "data": [{
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            }],
            "total": 1,
            "page": 1,
            "pageSize": 10
        }

        mock_get_collection_async.return_value = mock_response

        start_time = time.time()
        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            path="/v2/licenses",
            rate_limit=1000  # Very high rate limit should still add minimal delay
        )
        end_time = time.time()

        assert len(result) == 1
        # Should complete quickly but not instantaneously due to rate limiting setup
        assert end_time - start_time < 1.0
        # Verify the async function was called (client will be different due to wrapper)
        mock_get_collection_async.assert_called_once()
        call_args = mock_get_collection_async.call_args
        assert call_args[0][1] == "/v2/licenses"  # endpoint
        assert call_args[1]["page"] == 1  # page parameter


class TestParallelLoadPaginatedAsync:
    """Test parallel_load_paginated_async functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

    @pytest.mark.asyncio
    @patch('t3api_utils.api.parallel.get_collection_async')
    async def test_single_page_response(self, mock_get_collection_async):
        """Test async loading when there's only one page."""
        mock_response: MetrcCollectionResponse = {
            "data": [{
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            }],
            "total": 1,
            "page": 1,
            "pageSize": 10
        }

        mock_get_collection_async.return_value = mock_response

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            path="/v2/licenses"
        )

        assert len(result) == 1
        assert result[0] == mock_response
        mock_get_collection_async.assert_called_once_with(self.mock_client, "/v2/licenses", page=1)

    @pytest.mark.asyncio
    @patch('t3api_utils.api.parallel.get_collection_async')
    async def test_multiple_pages_response(self, mock_get_collection_async):
        """Test async loading when there are multiple pages."""
        def mock_method_side_effect(client, path, page=1, **kwargs):
            if page == 1:
                return {
                    "data": [{
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            }],
                    "total": 25,
                    "page": 1,
                    "pageSize": 10
                }
            elif page == 2:
                return {
                    "data": [{"id": "2", "licenseNumber": "LIC-002", "licenseName": "Company 2"}],
                    "total": 25,
                    "page": 2,
                    "pageSize": 10
                }
            elif page == 3:
                return {
                    "data": [{"id": "3", "licenseNumber": "LIC-003", "licenseName": "Company 3"}],
                    "total": 25,
                    "page": 3,
                    "pageSize": 10
                }

        mock_get_collection_async.side_effect = mock_method_side_effect

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            path="/v2/licenses"
        )

        # Should return 3 pages total (25 items / 10 per page = 3 pages)
        assert len(result) == 3
        assert mock_get_collection_async.call_count == 3

    @pytest.mark.asyncio
    @patch('t3api_utils.api.parallel.get_collection_async')
    async def test_batched_processing(self, mock_get_collection_async):
        """Test batched processing functionality."""
        def mock_method_side_effect(client, path, page=1, **kwargs):
            return {
                "data": [{"id": str(page), "licenseNumber": f"LIC-{page:03d}", "licenseName": f"Company {page}"}],
                "total": 50,  # 5 pages total
                "page": page,
                "pageSize": 10
            }

        mock_get_collection_async.side_effect = mock_method_side_effect

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            path="/v2/licenses",
            batch_size=2  # Process in batches of 2
        )

        # Should return 5 pages total
        assert len(result) == 5
        assert mock_get_collection_async.call_count == 5


class TestLoadAllDataSync:
    """Test load_all_data_sync functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

        # Add required attributes for asyncio wrapper
        from t3api_utils.http.utils import HTTPConfig, RetryPolicy
        self.mock_client._config = HTTPConfig()
        self.mock_client._retry_policy = RetryPolicy()
        self.mock_client._logging_hooks = None
        self.mock_client._extra_headers = {}
        self.mock_client._access_token = "test_token"

    def test_data_extraction(self):
        """Test that data is properly extracted from paginated responses."""
        mock_responses = [
            {
                "data": [
                    {
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            },
                    {"id": "2", "licenseNumber": "LIC-002", "licenseName": "Company 2"},
                ],
                "total": 4,
                "page": 1,
                "pageSize": 2
            },
            {
                "data": [
                    {"id": "3", "licenseNumber": "LIC-003", "licenseName": "Company 3"},
                    {"id": "4", "licenseNumber": "LIC-004", "licenseName": "Company 4"},
                ],
                "total": 4,
                "page": 2,
                "pageSize": 2
            }
        ]

        with patch('t3api_utils.api.parallel.parallel_load_paginated_async', return_value=mock_responses):
            result: List[Any] = load_all_data_sync(
                client=self.mock_client,
                path="/v2/licenses"
            )

        # Should return flattened data from both pages
        assert len(result) == 4
        assert all("id" in item for item in result)
        assert all("licenseNumber" in item for item in result)


class TestLoadAllDataAsync:
    """Test load_all_data_async functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

    @pytest.mark.asyncio
    async def test_data_extraction(self):
        """Test that data is properly extracted from paginated responses."""
        mock_responses = [
            {
                "data": [
                    {
                "id": 1,
                "hostname": "ca.metrc.com",
                "licenseNumber": "LIC-001",
                "dataModel": "LICENSE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            },
                    {"id": "2", "licenseNumber": "LIC-002", "licenseName": "Company 2"},
                ],
                "total": 4,
                "page": 1,
                "pageSize": 2
            },
            {
                "data": [
                    {"id": "3", "licenseNumber": "LIC-003", "licenseName": "Company 3"},
                    {"id": "4", "licenseNumber": "LIC-004", "licenseName": "Company 4"},
                ],
                "total": 4,
                "page": 2,
                "pageSize": 2
            }
        ]

        with patch('t3api_utils.api.parallel.parallel_load_paginated_async', return_value=mock_responses):
            result: List[Any] = await load_all_data_async(
                client=self.mock_client,
                path="/v2/licenses"
            )

        # Should return flattened data from both pages
        assert len(result) == 4
        assert all("id" in item for item in result)
        assert all("licenseNumber" in item for item in result)


class TestParallelLoadCollectionEnhanced:
    """Test parallel_load_collection_enhanced functionality."""

    def test_enhanced_collection_loading(self):
        """Test enhanced collection loading with rate limiting."""
        mock_response = {
            "total": 5,
            "pageSize": 10,
            "data": [{"id": "1"}] * 5
        }

        mock_method = MagicMock(return_value=mock_response)

        result: List[Any] = parallel_load_collection_enhanced(
            method=mock_method,
            max_workers=2,
            rate_limit=100
        )

        assert len(result) == 1  # Single page
        assert result[0] == mock_response
        mock_method.assert_called_once_with(page=1)

    def test_no_rate_limiting(self):
        """Test enhanced function works without rate limiting."""
        mock_response = {
            "total": 5,
            "pageSize": 10,
            "data": [{"id": "1"}] * 5
        }

        mock_method = MagicMock(return_value=mock_response)

        result: List[Any] = parallel_load_collection_enhanced(
            method=mock_method,
            rate_limit=None  # No rate limiting
        )

        assert len(result) == 1
        assert result[0] == mock_response
        mock_method.assert_called_once_with(page=1)