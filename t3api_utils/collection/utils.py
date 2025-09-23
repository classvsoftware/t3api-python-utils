"""Collection utilities for parallel API data loading.

This module provides both legacy and enhanced parallel loading capabilities,
supporting both the original t3api-based functions and new httpx-based clients.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from t3api_utils.api.interfaces import MetrcCollectionResponse, MetrcObject
from t3api_utils.interfaces import P
from t3api_utils.logging import get_logger

logger = get_logger(__name__)


def parallel_load_collection(
    method: Callable[P, MetrcCollectionResponse],
    max_workers: int | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> List[MetrcCollectionResponse]:
    """
    Fetches paginated responses in parallel using a thread pool.
    """
    logger.info("Starting parallel data load")
    first_response = method(*args, **kwargs)

    if first_response["total"] is None:
        raise ValueError("Response missing required `total` attribute.")

    total = first_response["total"]
    responses: List[MetrcCollectionResponse | None] = [None] * 1  # seed with first response

    page_size = first_response.get("pageSize")
    if page_size is None:
        page_size = len(first_response["data"])
    if page_size is None or page_size == 0:
        raise ValueError("Unable to determine page size from first response.")

    num_pages = (total + page_size - 1) // page_size
    logger.info(
        f"Total records: {total}, page size: {page_size}, total pages: {num_pages}"
    )

    responses = [None] * num_pages
    responses[0] = first_response

    def fetch_page(page_number: int) -> tuple[int, MetrcCollectionResponse]:
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


def extract_data(*, responses: List[MetrcCollectionResponse]) -> List[MetrcObject]:
    """
    Flatten a list of MetrcCollectionResponse objects that each have a `.data` property
    into a single list of MetrcObject items.

    Args:
        responses: A list of MetrcCollectionResponse objects.

    Returns:
        List[MetrcObject]: A flattened list of all items from the `.data` attributes.

    Example:
        >>> extract_data([Response1(data=[1, 2]), Response2(data=[3])])
        [1, 2, 3]
    """
    # Use nested list comprehension to flatten all `.data` lists into one
    return [item for response in responses for item in response["data"]]
