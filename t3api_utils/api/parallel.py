"""Enhanced parallel API utilities for T3 API client.

This module provides enhanced parallel loading capabilities that work with
our httpx-based T3APIClient, including async support, rate limiting, and
batching features.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import (Any, Awaitable, Callable, Dict, List, Optional, TypeVar,
                    Union, cast)

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse
from t3api_utils.api.operations import get_collection_async
from t3api_utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
PaginatedT = TypeVar("PaginatedT", bound=MetrcCollectionResponse)


class RateLimiter:
    """Simple rate limiter to avoid overwhelming the API."""

    def __init__(self, requests_per_second: float = 10.0) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second allowed
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        self.last_request_time = 0.0

    def acquire(self) -> None:
        """Block until it's safe to make another request."""
        if self.min_interval <= 0:
            return

        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    async def acquire_async(self) -> None:
        """Async version of acquire."""
        if self.min_interval <= 0:
            return

        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()


def parallel_load_paginated_sync(
    client: T3APIClient,
    path: str,
    max_workers: Optional[int] = None,
    rate_limit: Optional[float] = 10.0,
    **method_kwargs: Any,
) -> List[PaginatedT]:
    """
    Load all pages of a paginated API endpoint in parallel (sync wrapper).

    This is a wrapper around the async implementation using asyncio.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active")
        max_workers: Maximum number of threads to use (maps to max_concurrent for async)
        rate_limit: Requests per second limit (None to disable)
        **method_kwargs: Arguments to pass to the API method

    Returns:
        List of paginated response objects, one per page

    Raises:
        ValueError: If response is invalid
        AttributeError: If client is not authenticated
    """
    # Create a temporary async client that uses the same config and auth
    # but runs in its own event loop to avoid conflicts
    import concurrent.futures

    def run_in_thread() -> List[PaginatedT]:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Import here to avoid circular imports
            from t3api_utils.api.client import T3APIClient as TempClient

            # Create a new client with the same config and auth
            temp_client = TempClient(
                config=client._config,
                retry_policy=client._retry_policy,
                logging_hooks=client._logging_hooks,
                headers=client._extra_headers,
            )
            if client.access_token:
                temp_client.set_access_token(client.access_token)

            return loop.run_until_complete(parallel_load_paginated_async(
                client=temp_client,
                path=path,
                max_concurrent=max_workers,
                rate_limit=rate_limit,
                **method_kwargs,
            ))
        finally:
            loop.close()

    # Run in a separate thread with its own event loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        return future.result()


async def parallel_load_paginated_async(
    client: T3APIClient,
    path: str,
    max_concurrent: Optional[int] = 10,
    rate_limit: Optional[float] = 10.0,
    batch_size: Optional[int] = None,
    **method_kwargs: Any,
) -> List[PaginatedT]:
    """
    Load all pages of a paginated API endpoint in parallel using async client.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active")
        max_concurrent: Maximum number of concurrent requests
        rate_limit: Requests per second limit (None to disable)
        batch_size: Process requests in batches of this size (None for no batching)
        **method_kwargs: Arguments to pass to the API method

    Returns:
        List of paginated response objects, one per page

    Raises:
        ValueError: If response is invalid
        AttributeError: If client is not authenticated
    """
    if not client.is_authenticated:
        raise AttributeError("Client must be authenticated before loading data")

    logger.info(f"Starting parallel async load for {path}")

    # Set up rate limiter
    rate_limiter = RateLimiter(rate_limit) if rate_limit else None

    # Fetch first page to determine pagination
    if rate_limiter:
        await rate_limiter.acquire_async()

    first_response = cast(PaginatedT, await get_collection_async(client, path, page=1, **method_kwargs))

    if 'total' not in first_response or 'pageSize' not in first_response:
        raise ValueError("Response must have 'total' and 'pageSize' fields")

    total_records = first_response["total"]
    page_size = first_response["pageSize"]
    num_pages = (total_records + page_size - 1) // page_size

    logger.info(f"Total records: {total_records}, page size: {page_size}, pages: {num_pages}")

    if num_pages <= 1:
        return [first_response]

    async def fetch_page(page_number: int) -> tuple[int, PaginatedT]:
        """Fetch a specific page."""
        if rate_limiter:
            await rate_limiter.acquire_async()

        logger.debug(f"Fetching page {page_number}")
        response = cast(PaginatedT, await get_collection_async(client, path, page=page_number, **method_kwargs))
        return page_number - 1, response  # Convert to 0-based index

    # Prepare responses list
    responses: List[PaginatedT] = [None] * num_pages  # type: ignore
    responses[0] = first_response

    remaining_pages = list(range(2, num_pages + 1))

    if batch_size and batch_size > 0:
        # Process in batches
        logger.info(f"Processing {len(remaining_pages)} pages in batches of {batch_size}")

        for i in range(0, len(remaining_pages), batch_size):
            batch_pages = remaining_pages[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}: pages {batch_pages[0]}-{batch_pages[-1]}")

            # Create semaphore for this batch
            semaphore = asyncio.Semaphore(max_concurrent or len(batch_pages))

            async def fetch_with_semaphore(page_num: int) -> tuple[int, PaginatedT]:
                async with semaphore:
                    return await fetch_page(page_num)

            # Execute batch
            batch_tasks = [fetch_with_semaphore(page_num) for page_num in batch_pages]
            batch_results = await asyncio.gather(*batch_tasks)

            # Store results
            for page_index, response in batch_results:
                responses[page_index] = response

            logger.info(f"Completed batch {i // batch_size + 1}")
    else:
        # Process all at once with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent or len(remaining_pages))

        async def fetch_with_semaphore(page_num: int) -> tuple[int, PaginatedT]:
            async with semaphore:
                return await fetch_page(page_num)

        # Create all tasks
        tasks = [fetch_with_semaphore(page_num) for page_num in remaining_pages]

        # Execute with progress tracking
        for i, task in enumerate(asyncio.as_completed(tasks)):
            page_index, response = await task
            responses[page_index] = response
            logger.info(f"Loaded page {page_index + 1} ({i + 1}/{len(remaining_pages)})")

    logger.info("Finished parallel async load")
    return [r for r in responses if r is not None]


def load_all_data_sync(
    client: T3APIClient,
    path: str,
    max_workers: Optional[int] = None,
    rate_limit: Optional[float] = 10.0,
    **method_kwargs: Any,
) -> List[T]:
    """
    Load all data from a paginated endpoint and flatten into a single list (sync).

    This is a wrapper around the async implementation using asyncio.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active")
        max_workers: Maximum number of threads to use (maps to max_concurrent for async)
        rate_limit: Requests per second limit (None to disable)
        **method_kwargs: Arguments to pass to the API method

    Returns:
        Flattened list of all data items across all pages
    """
    # Create a temporary async client that uses the same config and auth
    # but runs in its own event loop to avoid conflicts
    import concurrent.futures

    def run_in_thread() -> List[T]:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Import here to avoid circular imports
            from t3api_utils.api.client import T3APIClient as TempClient

            # Create a new client with the same config and auth
            temp_client = TempClient(
                config=client._config,
                retry_policy=client._retry_policy,
                logging_hooks=client._logging_hooks,
                headers=client._extra_headers,
            )
            if client.access_token:
                temp_client.set_access_token(client.access_token)

            return loop.run_until_complete(load_all_data_async(
                client=temp_client,
                path=path,
                max_concurrent=max_workers,
                rate_limit=rate_limit,
                **method_kwargs,
            ))
        finally:
            loop.close()

    # Run in a separate thread with its own event loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        return future.result()


async def load_all_data_async(
    client: T3APIClient,
    path: str,
    max_concurrent: Optional[int] = 10,
    rate_limit: Optional[float] = 10.0,
    batch_size: Optional[int] = None,
    **method_kwargs: Any,
) -> List[T]:
    """
    Load all data from a paginated endpoint and flatten into a single list (async).

    This is a convenience function that combines parallel_load_paginated_async
    with data extraction.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active")
        max_concurrent: Maximum number of concurrent requests
        rate_limit: Requests per second limit (None to disable)
        batch_size: Process requests in batches of this size (None for no batching)
        **method_kwargs: Arguments to pass to the API method

    Returns:
        Flattened list of all data items across all pages
    """
    responses: List[MetrcCollectionResponse] = await parallel_load_paginated_async(
        client=client,
        path=path,
        max_concurrent=max_concurrent,
        rate_limit=rate_limit,
        batch_size=batch_size,
        **method_kwargs,
    )

    # Extract all data items
    all_data: List[T] = []
    for response in responses:
        all_data.extend(cast(List[T], response["data"]))

    return all_data


# Backwards compatibility - enhanced version of the original function
def parallel_load_collection_enhanced(
    method: Callable[..., PaginatedT],
    max_workers: Optional[int] = None,
    rate_limit: Optional[float] = None,
    **method_kwargs: Any,
) -> List[PaginatedT]:
    """
    Enhanced version of the original parallel_load_collection with rate limiting.

    This function maintains backwards compatibility with the original interface
    while adding rate limiting capabilities.

    Args:
        method: Callable that returns a paginated response
        max_workers: Maximum number of threads to use
        rate_limit: Requests per second limit (None to disable)
        **method_kwargs: Arguments to pass to the method

    Returns:
        List of paginated response objects
    """
    logger.info("Starting enhanced parallel data load")

    # Set up rate limiter
    rate_limiter = RateLimiter(rate_limit) if rate_limit else None

    # Fetch first page
    if rate_limiter:
        rate_limiter.acquire()

    first_response = method(page=1, **method_kwargs)

    if "total" not in first_response or first_response["total"] is None:
        raise ValueError("Response missing required `total` field.")

    total = first_response["total"]

    page_size = first_response.get("pageSize")
    if page_size is None:
        data = first_response.get("data", [])
        page_size = len(cast(List[Any], data)) if data is not None else 0
    if page_size is None or page_size == 0:
        raise ValueError("Unable to determine page size from first response.")

    # Type assertion since we know page_size is int at this point
    assert isinstance(page_size, int)
    num_pages = (total + page_size - 1) // page_size
    logger.info(f"Total records: {total}, page size: {page_size}, total pages: {num_pages}")

    if num_pages <= 1:
        return [first_response]

    responses: List[PaginatedT] = [None] * num_pages  # type: ignore
    responses[0] = first_response

    def fetch_page(page_number: int) -> tuple[int, PaginatedT]:
        if rate_limiter:
            rate_limiter.acquire()

        logger.debug(f"Fetching page {page_number + 1}")
        response = method(page=page_number + 1, **method_kwargs)
        return page_number, response

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_page, i) for i in range(1, num_pages)]
        for count, future in enumerate(as_completed(futures), start=1):
            page_number, response = future.result()
            responses[page_number] = response
            logger.info(f"Loaded page {page_number + 1} ({count}/{num_pages - 1})")

    logger.info("Finished enhanced parallel loading")
    return [r for r in responses if r is not None]