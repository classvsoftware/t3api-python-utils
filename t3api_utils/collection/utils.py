"""Collection utilities for parallel API data loading.

This module provides both legacy and enhanced parallel loading capabilities,
supporting both the original t3api-based functions and new httpx-based clients.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional, Union

from t3api_utils.interfaces import HasData, P, T
from t3api_utils.logging import get_logger

# Import enhanced parallel utilities
from t3api_utils.api.client import T3APIClient, AsyncT3APIClient
from t3api_utils.api.models import License, Package
from t3api_utils.api.parallel import (
    load_all_data_sync,
    load_all_data_async,
    parallel_load_paginated_sync,
    parallel_load_paginated_async,
    parallel_load_collection_enhanced,
)

logger = get_logger(__name__)

def parallel_load_collection(
    method: Callable[P, T],
    max_workers: int | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> List[T]:
    """
    Fetches paginated responses in parallel using a thread pool.
    """
    logger.info("Starting parallel data load")
    first_response = method(*args, **kwargs)

    if not hasattr(first_response, "total") or first_response.total is None:
        raise ValueError("Response missing required `total` attribute.")

    total = first_response.total
    responses: List[T | None] = [None] * 1  # seed with first response

    page_size = getattr(first_response, "page_size", None)
    if page_size is None:
        page_size = len(first_response) if hasattr(first_response, "__len__") else None
    if page_size is None or page_size == 0:
        raise ValueError("Unable to determine page size from first response.")

    num_pages = (total + page_size - 1) // page_size
    logger.info(f"Total records: {total}, page size: {page_size}, total pages: {num_pages}")

    responses = [None] * num_pages
    responses[0] = first_response

    def fetch_page(page_number: int) -> tuple[int, T]:
        logger.debug(f"Fetching page {page_number + 1}")
        response = method(*args, **kwargs, page=page_number + 1)  # type: ignore
        return page_number, response

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_page, i) for i in range(1, num_pages)]
        for count, future in enumerate(as_completed(futures), start=1):
            page_number, response = future.result()
            responses[page_number] = response
            logger.info(f"Loaded page {page_number + 1} ({count}/{num_pages - 1})")

    logger.info("Finished loading all pages")
    return [r for r in responses if r is not None]


# Enhanced functions for httpx-based API clients

def load_all_licenses(
    client: T3APIClient,
    max_workers: Optional[int] = None,
    rate_limit: Optional[float] = 10.0,
    **kwargs: object,
) -> List[License]:
    """
    Load all licenses using the new httpx-based client with parallel loading.

    Args:
        client: Authenticated T3APIClient instance
        max_workers: Maximum number of threads to use
        rate_limit: Requests per second limit (None to disable)
        **kwargs: Additional arguments to pass to get_licenses

    Returns:
        List of all License objects across all pages
    """
    return load_all_data_sync(
        client=client,
        method_name="get_licenses",
        max_workers=max_workers,
        rate_limit=rate_limit,
        **kwargs,
    )


def load_all_packages(
    client: T3APIClient,
    license_number: str,
    max_workers: Optional[int] = None,
    rate_limit: Optional[float] = 10.0,
    **kwargs: object,
) -> List[Package]:
    """
    Load all packages for a license using the new httpx-based client.

    Args:
        client: Authenticated T3APIClient instance
        license_number: License number to get packages for
        max_workers: Maximum number of threads to use
        rate_limit: Requests per second limit (None to disable)
        **kwargs: Additional arguments to pass to get_packages

    Returns:
        List of all Package objects across all pages
    """
    return load_all_data_sync(
        client=client,
        method_name="get_packages",
        license_number=license_number,
        max_workers=max_workers,
        rate_limit=rate_limit,
        **kwargs,
    )


async def load_all_licenses_async(
    client: AsyncT3APIClient,
    max_concurrent: Optional[int] = 10,
    rate_limit: Optional[float] = 10.0,
    batch_size: Optional[int] = None,
    **kwargs: object,
) -> List[License]:
    """
    Load all licenses asynchronously using the new httpx-based client.

    Args:
        client: Authenticated AsyncT3APIClient instance
        max_concurrent: Maximum number of concurrent requests
        rate_limit: Requests per second limit (None to disable)
        batch_size: Process requests in batches of this size
        **kwargs: Additional arguments to pass to get_licenses

    Returns:
        List of all License objects across all pages
    """
    return await load_all_data_async(
        client=client,
        method_name="get_licenses",
        max_concurrent=max_concurrent,
        rate_limit=rate_limit,
        batch_size=batch_size,
        **kwargs,
    )


async def load_all_packages_async(
    client: AsyncT3APIClient,
    license_number: str,
    max_concurrent: Optional[int] = 10,
    rate_limit: Optional[float] = 10.0,
    batch_size: Optional[int] = None,
    **kwargs: object,
) -> List[Package]:
    """
    Load all packages for a license asynchronously using the new httpx-based client.

    Args:
        client: Authenticated AsyncT3APIClient instance
        license_number: License number to get packages for
        max_concurrent: Maximum number of concurrent requests
        rate_limit: Requests per second limit (None to disable)
        batch_size: Process requests in batches of this size
        **kwargs: Additional arguments to pass to get_packages

    Returns:
        List of all Package objects across all pages
    """
    return await load_all_data_async(
        client=client,
        method_name="get_packages",
        license_number=license_number,
        max_concurrent=max_concurrent,
        rate_limit=rate_limit,
        batch_size=batch_size,
        **kwargs,
    )


def extract_data(responses: List[HasData[T]]) -> List[T]:
    """
    Flatten a list of response-like objects that each have a `.data` property
    into a single list of data items, preserving their type.

    Args:
        responses (List[HasData[T]]): A list of objects that each implement the HasData protocol.

    Returns:
        List[T]: A flattened list of all items from the `.data` attributes.

    Example:
        >>> extract_data([Response1(data=[1, 2]), Response2(data=[3])])
        [1, 2, 3]
    """
    # Use nested list comprehension to flatten all `.data` lists into one
    return [item for response in responses for item in response.data]
