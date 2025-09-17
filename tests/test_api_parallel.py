"""Tests for parallel API utilities."""
import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List, Any

from t3api_utils.api.parallel import (
    RateLimiter,
    parallel_load_paginated_sync,
    parallel_load_paginated_async,
    load_all_data_sync,
    load_all_data_async,
    parallel_load_collection_enhanced,
)
from t3api_utils.api.client import T3APIClient, AsyncT3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse


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

    def test_single_page_response(self):
        """Test loading when there's only one page."""
        # Mock response with single page
        mock_response: MetrcCollectionResponse = {
            "data": [{"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"}],
            "total": 1,
            "page": 1,
            "pageSize": 10
        }

        mock_method = MagicMock(return_value=mock_response)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            method_name="get_licenses"
        )

        assert len(result) == 1
        assert result[0] == mock_response
        mock_method.assert_called_once_with(page=1)

    def test_multiple_pages_response(self):
        """Test loading when there are multiple pages."""
        def mock_method_side_effect(page=1, **kwargs):
            if page == 1:
                return {
                    "data": [{"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"}],
                    "total": 25,
                    "page": 1,
                    "pageSize": 10
                }
            elif page == 2:
                return {
                    "data": [{"id": "2", "licenseNumber": "LIC-002", "legalName": "Company 2"}],
                    "total": 25,
                    "page": 2,
                    "pageSize": 10
                }
            elif page == 3:
                return {
                    "data": [{"id": "3", "licenseNumber": "LIC-003", "legalName": "Company 3"}],
                    "total": 25,
                    "page": 3,
                    "pageSize": 10
                }

        mock_method = MagicMock(side_effect=mock_method_side_effect)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            method_name="get_licenses"
        )

        # Should return 3 pages total (25 items / 10 per page = 3 pages)
        assert len(result) == 3
        assert mock_method.call_count == 3

    def test_rate_limiting_applied(self):
        """Test that rate limiting is properly applied."""
        mock_response: MetrcCollectionResponse = {
            "data": [{"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"}],
            "total": 1,
            "page": 1,
            "pageSize": 10
        }

        mock_method = MagicMock(return_value=mock_response)
        self.mock_client.get_licenses = mock_method

        start_time = time.time()
        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            method_name="get_licenses",
            rate_limit=1000  # Very high rate limit should still add minimal delay
        )
        end_time = time.time()

        assert len(result) == 1
        # Should complete quickly but not instantaneously due to rate limiting setup
        assert end_time - start_time < 1.0


class TestParallelLoadPaginatedAsync:
    """Test parallel_load_paginated_async functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=AsyncT3APIClient)
        self.mock_client.is_authenticated = True

    @pytest.mark.asyncio
    async def test_single_page_response(self):
        """Test async loading when there's only one page."""
        mock_response: MetrcCollectionResponse = {
            "data": [{"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"}],
            "total": 1,
            "page": 1,
            "pageSize": 10
        }

        mock_method = AsyncMock(return_value=mock_response)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            method_name="get_licenses"
        )

        assert len(result) == 1
        assert result[0] == mock_response
        mock_method.assert_called_once_with(page=1)

    @pytest.mark.asyncio
    async def test_multiple_pages_response(self):
        """Test async loading when there are multiple pages."""
        async def mock_method_side_effect(page=1, **kwargs):
            if page == 1:
                return {
                    "data": [{"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"}],
                    "total": 25,
                    "page": 1,
                    "pageSize": 10
                }
            elif page == 2:
                return {
                    "data": [{"id": "2", "licenseNumber": "LIC-002", "legalName": "Company 2"}],
                    "total": 25,
                    "page": 2,
                    "pageSize": 10
                }
            elif page == 3:
                return {
                    "data": [{"id": "3", "licenseNumber": "LIC-003", "legalName": "Company 3"}],
                    "total": 25,
                    "page": 3,
                    "pageSize": 10
                }

        mock_method = AsyncMock(side_effect=mock_method_side_effect)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            method_name="get_licenses"
        )

        # Should return 3 pages total (25 items / 10 per page = 3 pages)
        assert len(result) == 3
        assert mock_method.call_count == 3

    @pytest.mark.asyncio
    async def test_batched_processing(self):
        """Test batched processing functionality."""
        async def mock_method_side_effect(page=1, **kwargs):
            return {
                "data": [{"id": str(page), "licenseNumber": f"LIC-{page:03d}", "legalName": f"Company {page}"}],
                "total": 50,  # 5 pages total
                "page": page,
                "pageSize": 10
            }

        mock_method = AsyncMock(side_effect=mock_method_side_effect)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            method_name="get_licenses",
            batch_size=2  # Process in batches of 2
        )

        # Should return 5 pages total
        assert len(result) == 5
        assert mock_method.call_count == 5


class TestLoadAllDataSync:
    """Test load_all_data_sync functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

    def test_data_extraction(self):
        """Test that data is properly extracted from paginated responses."""
        mock_responses = [
            {
                "data": [
                    {"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"},
                    {"id": "2", "licenseNumber": "LIC-002", "legalName": "Company 2"},
                ],
                "total": 4,
                "page": 1,
                "pageSize": 2
            },
            {
                "data": [
                    {"id": "3", "licenseNumber": "LIC-003", "legalName": "Company 3"},
                    {"id": "4", "licenseNumber": "LIC-004", "legalName": "Company 4"},
                ],
                "total": 4,
                "page": 2,
                "pageSize": 2
            }
        ]

        with patch('t3api_utils.api.parallel.parallel_load_paginated_sync', return_value=mock_responses):
            result: List[Any] = load_all_data_sync(
                client=self.mock_client,
                method_name="get_licenses"
            )

        # Should return flattened data from both pages
        assert len(result) == 4
        assert all("id" in item for item in result)
        assert all("licenseNumber" in item for item in result)


class TestLoadAllDataAsync:
    """Test load_all_data_async functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=AsyncT3APIClient)
        self.mock_client.is_authenticated = True

    @pytest.mark.asyncio
    async def test_data_extraction(self):
        """Test that data is properly extracted from paginated responses."""
        mock_responses = [
            {
                "data": [
                    {"id": "1", "licenseNumber": "LIC-001", "legalName": "Company 1"},
                    {"id": "2", "licenseNumber": "LIC-002", "legalName": "Company 2"},
                ],
                "total": 4,
                "page": 1,
                "pageSize": 2
            },
            {
                "data": [
                    {"id": "3", "licenseNumber": "LIC-003", "legalName": "Company 3"},
                    {"id": "4", "licenseNumber": "LIC-004", "legalName": "Company 4"},
                ],
                "total": 4,
                "page": 2,
                "pageSize": 2
            }
        ]

        with patch('t3api_utils.api.parallel.parallel_load_paginated_async', return_value=mock_responses):
            result: List[Any] = await load_all_data_async(
                client=self.mock_client,
                method_name="get_licenses"
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