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
from t3api_utils.api.models import LicensesResponse, License


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
        """Test rate limiter enforces delays."""
        # 2 requests per second = 0.5 second intervals
        limiter = RateLimiter(2.0)

        start_time = time.time()
        limiter.acquire()  # First request - no delay
        limiter.acquire()  # Second request - should delay
        end_time = time.time()

        # Should take at least 0.5 seconds
        assert end_time - start_time >= 0.4  # Allow some tolerance

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
        """Test async rate limiter enforces delays."""
        # 2 requests per second = 0.5 second intervals
        limiter = RateLimiter(2.0)

        start_time = time.time()
        await limiter.acquire_async()  # First request - no delay
        await limiter.acquire_async()  # Second request - should delay
        end_time = time.time()

        # Should take at least 0.5 seconds
        assert end_time - start_time >= 0.4  # Allow some tolerance


class TestParallelLoadPaginatedSync:
    """Test sync parallel paginated loading."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

    def test_single_page_response(self):
        """Test loading when there's only one page."""
        # Mock response with single page
        mock_response = LicensesResponse(
            data=[License(id="1", license_number="LIC-001", legal_name="Company 1")],
            total=1,
            page=1,
            page_size=10
        )

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
        """Test loading multiple pages in parallel."""
        def mock_method_side_effect(page=1, **kwargs):
            if page == 1:
                return LicensesResponse(
                    data=[License(id="1", license_number="LIC-001", legal_name="Company 1")],
                    total=25,
                    page=1,
                    page_size=10
                )
            elif page == 2:
                return LicensesResponse(
                    data=[License(id="2", license_number="LIC-002", legal_name="Company 2")],
                    total=25,
                    page=2,
                    page_size=10
                )
            elif page == 3:
                return LicensesResponse(
                    data=[License(id="3", license_number="LIC-003", legal_name="Company 3")],
                    total=25,
                    page=3,
                    page_size=10
                )

        mock_method = MagicMock(side_effect=mock_method_side_effect)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = parallel_load_paginated_sync(
            client=self.mock_client,
            method_name="get_licenses"
        )

        assert len(result) == 3
        assert mock_method.call_count == 3
        # Verify all pages were called
        assert any(call.kwargs.get('page') == 1 for call in mock_method.call_args_list)
        assert any(call.kwargs.get('page') == 2 for call in mock_method.call_args_list)
        assert any(call.kwargs.get('page') == 3 for call in mock_method.call_args_list)

    def test_not_authenticated_error(self):
        """Test error when client is not authenticated."""
        self.mock_client.is_authenticated = False

        with pytest.raises(AttributeError, match="authenticated"):
            parallel_load_paginated_sync(
                client=self.mock_client,
                method_name="get_licenses"
            )

    def test_invalid_method_error(self):
        """Test error when method doesn't exist."""
        with pytest.raises(ValueError, match="no callable method"):
            parallel_load_paginated_sync(
                client=self.mock_client,
                method_name="nonexistent_method"
            )

    def test_invalid_response_error(self):
        """Test error when response lacks pagination attributes."""
        mock_response = MagicMock()
        del mock_response.total  # Remove required attribute

        mock_method = MagicMock(return_value=mock_response)
        self.mock_client.get_licenses = mock_method

        with pytest.raises(ValueError, match="total.*page_size"):
            parallel_load_paginated_sync(
                client=self.mock_client,
                method_name="get_licenses"
            )

    @patch('t3api_utils.api.parallel.RateLimiter')
    def test_rate_limiting_applied(self, mock_rate_limiter_class):
        """Test that rate limiting is properly applied."""
        mock_rate_limiter = MagicMock()
        mock_rate_limiter_class.return_value = mock_rate_limiter

        mock_response = LicensesResponse(
            data=[License(id="1", license_number="LIC-001", legal_name="Company 1")],
            total=1,
            page=1,
            page_size=10
        )

        mock_method = MagicMock(return_value=mock_response)
        self.mock_client.get_licenses = mock_method

        parallel_load_paginated_sync(
            client=self.mock_client,
            method_name="get_licenses",
            rate_limit=5.0
        )

        # Verify rate limiter was created and used
        mock_rate_limiter_class.assert_called_once_with(5.0)
        mock_rate_limiter.acquire.assert_called_once()


class TestParallelLoadPaginatedAsync:
    """Test async parallel paginated loading."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=AsyncT3APIClient)
        self.mock_client.is_authenticated = True

    @pytest.mark.asyncio
    async def test_single_page_response(self):
        """Test async loading when there's only one page."""
        mock_response = LicensesResponse(
            data=[License(id="1", license_number="LIC-001", legal_name="Company 1")],
            total=1,
            page=1,
            page_size=10
        )

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
        """Test async loading multiple pages."""
        async def mock_method_side_effect(page=1, **kwargs):
            if page == 1:
                return LicensesResponse(
                    data=[License(id="1", license_number="LIC-001", legal_name="Company 1")],
                    total=25,
                    page=1,
                    page_size=10
                )
            elif page == 2:
                return LicensesResponse(
                    data=[License(id="2", license_number="LIC-002", legal_name="Company 2")],
                    total=25,
                    page=2,
                    page_size=10
                )
            elif page == 3:
                return LicensesResponse(
                    data=[License(id="3", license_number="LIC-003", legal_name="Company 3")],
                    total=25,
                    page=3,
                    page_size=10
                )

        mock_method = AsyncMock(side_effect=mock_method_side_effect)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            method_name="get_licenses"
        )

        assert len(result) == 3
        assert mock_method.call_count == 3

    @pytest.mark.asyncio
    async def test_batched_processing(self):
        """Test processing pages in batches."""
        async def mock_method_side_effect(page=1, **kwargs):
            return LicensesResponse(
                data=[License(id=str(page), license_number=f"LIC-{page:03d}", legal_name=f"Company {page}")],
                total=50,  # 5 pages total
                page=page,
                page_size=10
            )

        mock_method = AsyncMock(side_effect=mock_method_side_effect)
        self.mock_client.get_licenses = mock_method

        result: List[Any] = await parallel_load_paginated_async(
            client=self.mock_client,
            method_name="get_licenses",
            batch_size=2  # Process in batches of 2
        )

        assert len(result) == 5
        assert mock_method.call_count == 5

    @pytest.mark.asyncio
    async def test_not_authenticated_error(self):
        """Test error when client is not authenticated."""
        self.mock_client.is_authenticated = False

        with pytest.raises(AttributeError, match="authenticated"):
            await parallel_load_paginated_async(
                client=self.mock_client,
                method_name="get_licenses"
            )


class TestLoadAllDataSync:
    """Test sync data loading convenience function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=T3APIClient)
        self.mock_client.is_authenticated = True

    @patch('t3api_utils.api.parallel.parallel_load_paginated_sync')
    def test_data_extraction(self, mock_parallel_load):
        """Test that data is properly extracted from paginated responses."""
        # Mock paginated responses
        mock_responses = [
            LicensesResponse(
                data=[
                    License(id="1", license_number="LIC-001", legal_name="Company 1"),
                    License(id="2", license_number="LIC-002", legal_name="Company 2"),
                ],
                total=4,
                page=1,
                page_size=2
            ),
            LicensesResponse(
                data=[
                    License(id="3", license_number="LIC-003", legal_name="Company 3"),
                    License(id="4", license_number="LIC-004", legal_name="Company 4"),
                ],
                total=4,
                page=2,
                page_size=2
            )
        ]
        mock_parallel_load.return_value = mock_responses

        result: List[Any] = load_all_data_sync(
            client=self.mock_client,
            method_name="get_licenses"
        )

        # Should return flattened list of all licenses
        assert len(result) == 4
        assert all(isinstance(item, License) for item in result)
        assert result[0].id == "1"
        assert result[3].id == "4"

        # Verify parallel_load_paginated_sync was called correctly
        mock_parallel_load.assert_called_once_with(
            client=self.mock_client,
            method_name="get_licenses",
            max_workers=None,
            rate_limit=10.0
        )


class TestLoadAllDataAsync:
    """Test async data loading convenience function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=AsyncT3APIClient)
        self.mock_client.is_authenticated = True

    @pytest.mark.asyncio
    @patch('t3api_utils.api.parallel.parallel_load_paginated_async')
    async def test_data_extraction(self, mock_parallel_load):
        """Test that data is properly extracted from paginated responses."""
        # Mock paginated responses
        mock_responses = [
            LicensesResponse(
                data=[
                    License(id="1", license_number="LIC-001", legal_name="Company 1"),
                    License(id="2", license_number="LIC-002", legal_name="Company 2"),
                ],
                total=4,
                page=1,
                page_size=2
            ),
            LicensesResponse(
                data=[
                    License(id="3", license_number="LIC-003", legal_name="Company 3"),
                    License(id="4", license_number="LIC-004", legal_name="Company 4"),
                ],
                total=4,
                page=2,
                page_size=2
            )
        ]
        mock_parallel_load.return_value = mock_responses

        result: List[Any] = await load_all_data_async(
            client=self.mock_client,
            method_name="get_licenses"
        )

        # Should return flattened list of all licenses
        assert len(result) == 4
        assert all(isinstance(item, License) for item in result)
        assert result[0].id == "1"
        assert result[3].id == "4"

        # Verify parallel_load_paginated_async was called correctly
        mock_parallel_load.assert_called_once_with(
            client=self.mock_client,
            method_name="get_licenses",
            max_concurrent=10,
            rate_limit=10.0,
            batch_size=None
        )


class TestParallelLoadCollectionEnhanced:
    """Test backwards compatibility function."""

    def test_enhanced_collection_loading(self):
        """Test enhanced version maintains compatibility."""
        def mock_method(page=1, **kwargs):
            if page == 1:
                response = MagicMock()
                response.total = 25
                response.page_size = 10
                response.__len__ = MagicMock(return_value=10)
                return response
            else:
                response = MagicMock()
                response.total = 25
                response.page_size = 10
                response.__len__ = MagicMock(return_value=10)
                return response

        with patch('time.sleep'):  # Avoid actual delays in tests
            result: List[Any] = parallel_load_collection_enhanced(
                method=mock_method,
                max_workers=2,
                rate_limit=100  # High rate limit to avoid delays
            )

        # Should return 3 pages (25 items / 10 per page = 3 pages)
        assert len(result) == 3

    def test_no_rate_limiting(self):
        """Test enhanced function works without rate limiting."""
        mock_response = MagicMock()
        mock_response.total = 5
        mock_response.page_size = 10
        mock_response.__len__ = MagicMock(return_value=5)

        mock_method = MagicMock(return_value=mock_response)

        result: List[Any] = parallel_load_collection_enhanced(
            method=mock_method,
            rate_limit=None  # No rate limiting
        )

        # Should have single page
        assert len(result) == 1
        mock_method.assert_called_once_with(page=1)