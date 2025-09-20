"""Collection utilities for parallel API data loading.

This module provides both legacy and enhanced parallel loading capabilities,
supporting both the original t3api-based functions and new httpx-based clients.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from t3api_utils.interfaces import HasData, P, T
from t3api_utils.logging import get_logger

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
    logger.info(
        f"Total records: {total}, page size: {page_size}, total pages: {num_pages}"
    )

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


def extract_data(*, responses: List[HasData[T]]) -> List[T]:
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
