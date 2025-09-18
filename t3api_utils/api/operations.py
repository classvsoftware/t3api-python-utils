"""Standalone T3 API operations that work with authenticated clients.

This module provides high-level operations for common T3 API endpoints
that can be called independently with an authenticated client instance.
"""
from __future__ import annotations

from typing import Any, Union, cast

from t3api_utils.api.client import T3APIClient, AsyncT3APIClient
from t3api_utils.api.interfaces import MetrcCollectionResponse
from t3api_utils.http.utils import T3HTTPError, arequest_json, request_json


def get_collection(
    client: T3APIClient,
    endpoint: str,
    *,
    page: int = 1,
    page_size: int = 100,
    **kwargs: Any,
) -> MetrcCollectionResponse:
    """Get a collection from any T3 API endpoint using a sync client.

    Args:
        client: Authenticated T3APIClient instance
        endpoint: API endpoint path (e.g., "/v2/licenses", "/v2/packages")
        page: Page number (1-based)
        page_size: Number of items per page
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
        "page": page,
        "pageSize": page_size,
        **kwargs,
    }

    try:
        response_data = request_json(
            client=client._client,
            method="GET",
            url=endpoint,
            params=params,
            policy=client._retry_policy,
            expected_status=200,
        )

        return cast(MetrcCollectionResponse, response_data)

    except T3HTTPError as e:
        raise T3HTTPError(f"Failed to get collection from {endpoint}: {e}", response=e.response) from e


async def get_collection_async(
    client: AsyncT3APIClient,
    endpoint: str,
    *,
    page: int = 1,
    page_size: int = 100,
    **kwargs: Any,
) -> MetrcCollectionResponse:
    """Get a collection from any T3 API endpoint using an async client.

    Args:
        client: Authenticated AsyncT3APIClient instance
        endpoint: API endpoint path (e.g., "/v2/licenses", "/v2/packages")
        page: Page number (1-based)
        page_size: Number of items per page
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
        "page": page,
        "pageSize": page_size,
        **kwargs,
    }

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