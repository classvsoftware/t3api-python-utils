from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List

from t3api_utils.interfaces import P, T, HasData


def parallel_load_collection(
    method: Callable[P, T],
    max_workers: int | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> List[T]:
    """
    Fetches paginated responses in parallel using a thread pool.

    Args:
        method: The function to call for each page. Must return a response with a `total` attribute.
        max_workers: Optional max number of threads to use.
        *args: Positional arguments for the method.
        **kwargs: Keyword arguments for the method.

    Returns:
        A list of full responses from each page.
    """
    first_response = method(*args, **kwargs)

    if not hasattr(first_response, "total") or first_response.total is None:
        raise ValueError("Response missing required `total` attribute.")

    total = first_response.total
    responses: List[T | None] = [None] * 1  # seed with first response

    # Try to infer page size from response object (if possible)
    page_size = getattr(first_response, "page_size", None)
    if page_size is None:
        # Fall back to len() if response is list-like
        page_size = len(first_response) if hasattr(first_response, "__len__") else None
    if page_size is None or page_size == 0:
        raise ValueError("Unable to determine page size from first response.")

    num_pages = (total + page_size - 1) // page_size
    responses = [None] * num_pages
    responses[0] = first_response

    def fetch_page(page_number: int) -> tuple[int, T]:
        response = method(*args, **kwargs, page=page_number + 1)  # type: ignore
        return page_number, response

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_page, i) for i in range(1, num_pages)]
        for future in as_completed(futures):
            page_number, response = future.result()
            responses[page_number] = response

    return [r for r in responses if r is not None]


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
