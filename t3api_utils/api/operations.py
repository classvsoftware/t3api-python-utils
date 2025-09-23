"""Standalone T3 API operations that work with authenticated clients.

This module provides high-level operations for T3 API endpoints that can be
called independently with an authenticated client instance.

Available operations:
- send_api_request / send_api_request_async: Most generic operation, supports any HTTP method,
  custom parameters, and doesn't assume response structure
- get_collection / get_collection_async: Specialized for paginated collection
  endpoints, automatically adds page/pageSize parameters
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Literal, Optional, Union, cast

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse
from t3api_utils.http.utils import T3HTTPError, arequest_json


def send_api_request(
    client: T3APIClient,
    path: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    expected_status: Union[int, tuple[int, ...]] = 200,
) -> Any:
    """Send a request to any T3 API endpoint (sync wrapper).

    This is the most flexible operation that doesn't assume any specific
    parameter structure or response format.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active", "/v2/facilities/123")
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
    # For sync wrapper, we need to handle the case where the client might have been
    # created in a different event loop context. The safest approach is to create
    # a new client instance for this operation.

    from t3api_utils.http.utils import request_json

    # Use the sync version of request_json directly with the client's underlying config
    if not client.is_authenticated:
        raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

    # Extract auth headers from the async client
    headers_dict = dict(headers) if headers else {}
    if client.access_token:
        headers_dict["Authorization"] = f"Bearer {client.access_token}"

    # Create a sync httpx client for this operation
    import httpx

    # Prepare client kwargs, handling optional parameters properly
    client_kwargs: Dict[str, Any] = {
        "base_url": client._config.host,
        "timeout": client._config.timeout,
        "verify": client._config.ssl_context,
    }

    if client._config.base_headers:
        client_kwargs["headers"] = client._config.base_headers

    if client._config.proxies:
        client_kwargs["proxies"] = client._config.proxies

    with httpx.Client(**client_kwargs) as sync_client:
        return request_json(
            client=sync_client,
            method=method,
            url=path,
            params=params,
            json_body=json_body,
            headers=headers_dict,
            policy=client._retry_policy,
            expected_status=expected_status,
        )


def get_collection(
    client: T3APIClient,
    path: str,
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
    """Get a collection from any T3 API endpoint (sync wrapper).

    This is a wrapper around the async implementation using asyncio.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active")
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
    # Use sync HTTP client to avoid event loop conflicts
    from t3api_utils.http.utils import request_json

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

    # Extract auth headers
    headers_dict = {}
    if client.access_token:
        headers_dict["Authorization"] = f"Bearer {client.access_token}"

    try:
        # Create a sync httpx client for this operation
        import httpx

        # Prepare client kwargs, handling optional parameters properly
        client_kwargs: Dict[str, Any] = {
            "base_url": client._config.host,
            "timeout": client._config.timeout,
            "verify": client._config.ssl_context,
        }

        if client._config.base_headers:
            client_kwargs["headers"] = client._config.base_headers

        if client._config.proxies:
            client_kwargs["proxies"] = client._config.proxies

        with httpx.Client(**client_kwargs) as sync_client:
            response_data = request_json(
                client=sync_client,
                method="GET",
                url=path,
                params=params,
                headers=headers_dict,
                policy=client._retry_policy,
                expected_status=200,
            )

            return cast(MetrcCollectionResponse, response_data)

    except T3HTTPError as e:
        raise T3HTTPError(f"Failed to get collection from {path}: {e}", response=e.response) from e


async def get_collection_async(
    client: T3APIClient,
    path: str,
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
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active")
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
            url=path,
            params=params,
            policy=client._retry_policy,
            expected_status=200,
        )

        return cast(MetrcCollectionResponse, response_data)

    except T3HTTPError as e:
        raise T3HTTPError(f"Failed to get collection from {path}: {e}", response=e.response) from e


async def send_api_request_async(
    client: T3APIClient,
    path: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    expected_status: Union[int, tuple[int, ...]] = 200,
) -> Any:
    """Send a request to any T3 API endpoint using an async client.

    This is the most flexible operation that doesn't assume any specific
    parameter structure or response format.

    Args:
        client: Authenticated T3APIClient instance
        path: API endpoint path (e.g., "/v2/licenses", "/v2/packages/active", "/v2/facilities/123")
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
            url=path,
            params=params,
            json_body=json_body,
            headers=headers,
            policy=client._retry_policy,
            expected_status=expected_status,
        )

        return response_data

    except T3HTTPError as e:
        raise T3HTTPError(f"Failed to get data from {path}: {e}", response=e.response) from e