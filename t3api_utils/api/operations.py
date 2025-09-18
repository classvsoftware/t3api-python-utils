"""Standalone T3 API operations that work with authenticated clients.

This module provides high-level operations for T3 API endpoints that can be
called independently with an authenticated client instance.

Available operations:
- get_data / get_data_async: Most generic operation, supports any HTTP method,
  custom parameters, and doesn't assume response structure
- get_collection / get_collection_async: Specialized for paginated collection
  endpoints, automatically adds page/pageSize parameters
"""
from __future__ import annotations

import asyncio
from typing import Any, Union, cast, Dict, Optional, List, Literal

from t3api_utils.api.client import T3APIClient, AsyncT3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse
from t3api_utils.http.utils import T3HTTPError, arequest_json


def get_data(
    client: T3APIClient,
    endpoint: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    expected_status: Union[int, tuple[int, ...]] = 200,
) -> Any:
    """Generic data retrieval from any T3 API endpoint using a sync client.

    This is the most flexible operation that doesn't assume any specific
    parameter structure or response format.

    Args:
        client: Authenticated T3APIClient instance
        endpoint: API endpoint path (e.g., "/v2/licenses", "/v2/packages", "/v2/facilities/123")
        method: HTTP method (default: "GET")
        params: Query parameters (optional)
        json_body: JSON request body for POST/PUT requests (optional)
        headers: Additional headers (optional)
        expected_status: Expected HTTP status code(s) (default: 200)

    Returns:
        Raw response data (could be dict, list, or any JSON-serializable type)

    Raises:
        T3HTTPError: If request fails or client not authenticated
    """
    # Create async client from sync client
    async_client = AsyncT3APIClient(
        config=client._config,
        retry_policy=client._retry_policy,
        logging_hooks=client._logging_hooks,
        headers=client._extra_headers,
    )
    # Set access token if available
    if client._access_token:
        async_client.set_access_token(client._access_token)

    # Run the async version
    async def _run() -> Any:
        async with async_client:
            return await get_data_async(
                client=async_client,
                endpoint=endpoint,
                method=method,
                params=params,
                json_body=json_body,
                headers=headers,
                expected_status=expected_status,
            )

    return asyncio.run(_run())


def get_collection(
    client: T3APIClient,
    endpoint: str,
    *,
    license_number: str,
    page: int = 1,
    page_size: int = 100,
    strict_pagination: bool = False,
    sort: Optional[str] = None,
    filter_logic: Literal["and", "or"] = "and",
    filter: Optional[List[str]] = None,
    **kwargs: Any,
) -> MetrcCollectionResponse:
    """Get a collection from any T3 API endpoint using a sync client.

    This is a wrapper around the async implementation using asyncio.

    Args:
        client: Authenticated T3APIClient instance
        endpoint: API endpoint path (e.g., "/v2/licenses", "/v2/packages")
        license_number: The unique identifier for the license (required)
        page: Page number (1-based, default: 1)
        page_size: Number of items per page (default: 100)
        strict_pagination: If enabled, out of bounds pages throw 400 (default: False)
        sort: Collection sort order (e.g., "label:asc")
        filter_logic: How filters are applied - "and" or "or" (default: "and")
        filter: List of collection filters (e.g., ["label__endswith:0003"])
        **kwargs: Additional query parameters

    Returns:
        MetrcCollectionResponse containing data from the endpoint

    Raises:
        T3HTTPError: If request fails or client not authenticated
    """
    # Create async client from sync client
    async_client = AsyncT3APIClient(
        config=client._config,
        retry_policy=client._retry_policy,
        logging_hooks=client._logging_hooks,
        headers=client._extra_headers,
    )
    # Set access token if available
    if client._access_token:
        async_client.set_access_token(client._access_token)

    # Run the async version
    async def _run() -> MetrcCollectionResponse:
        async with async_client:
            return await get_collection_async(
                client=async_client,
                endpoint=endpoint,
                license_number=license_number,
                page=page,
                page_size=page_size,
                strict_pagination=strict_pagination,
                sort=sort,
                filter_logic=filter_logic,
                filter=filter,
                **kwargs,
            )

    return asyncio.run(_run())


async def get_collection_async(
    client: AsyncT3APIClient,
    endpoint: str,
    *,
    license_number: str,
    page: int = 1,
    page_size: int = 100,
    strict_pagination: bool = False,
    sort: Optional[str] = None,
    filter_logic: Literal["and", "or"] = "and",
    filter: Optional[List[str]] = None,
    **kwargs: Any,
) -> MetrcCollectionResponse:
    """Get a collection from any T3 API endpoint using an async client.

    Args:
        client: Authenticated AsyncT3APIClient instance
        endpoint: API endpoint path (e.g., "/v2/licenses", "/v2/packages")
        license_number: The unique identifier for the license (required)
        page: Page number (1-based, default: 1)
        page_size: Number of items per page (default: 100)
        strict_pagination: If enabled, out of bounds pages throw 400 (default: False)
        sort: Collection sort order (e.g., "label:asc")
        filter_logic: How filters are applied - "and" or "or" (default: "and")
        filter: List of collection filters (e.g., ["label__endswith:0003"])
        **kwargs: Additional query parameters

    Returns:
        MetrcCollectionResponse containing data from the endpoint

    Raises:
        T3HTTPError: If request fails or client not authenticated
    """
    if not client.is_authenticated:
        raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

    # Prepare query parameters
    params = {
        "licenseNumber": license_number,
        "page": page,
        "pageSize": page_size,
        "strictPagination": strict_pagination,
        "filterLogic": filter_logic,
        **kwargs,
    }

    # Add optional parameters only if they're provided
    if sort is not None:
        params["sort"] = sort
    if filter is not None:
        params["filter"] = filter

    try:
        response_data = await arequest_json(
            aclient=client._client,
            method="GET",
            url=endpoint,
            params=params,
            policy=client._retry_policy,
            expected_status=200,
        )

        return cast(MetrcCollectionResponse, response_data)

    except T3HTTPError as e:
        raise T3HTTPError(f"Failed to get collection from {endpoint}: {e}", response=e.response) from e


async def get_data_async(
    client: AsyncT3APIClient,
    endpoint: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    expected_status: Union[int, tuple[int, ...]] = 200,
) -> Any:
    """Generic data retrieval from any T3 API endpoint using an async client.

    This is the most flexible operation that doesn't assume any specific
    parameter structure or response format.

    Args:
        client: Authenticated AsyncT3APIClient instance
        endpoint: API endpoint path (e.g., "/v2/licenses", "/v2/packages", "/v2/facilities/123")
        method: HTTP method (default: "GET")
        params: Query parameters (optional)
        json_body: JSON request body for POST/PUT requests (optional)
        headers: Additional headers (optional)
        expected_status: Expected HTTP status code(s) (default: 200)

    Returns:
        Raw response data (could be dict, list, or any JSON-serializable type)

    Raises:
        T3HTTPError: If request fails or client not authenticated
    """
    if not client.is_authenticated:
        raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

    try:
        response_data = await arequest_json(
            aclient=client._client,
            method=method,
            url=endpoint,
            params=params,
            json_body=json_body,
            headers=headers,
            policy=client._retry_policy,
            expected_status=expected_status,
        )

        return response_data

    except T3HTTPError as e:
        raise T3HTTPError(f"Failed to get data from {endpoint}: {e}", response=e.response) from e