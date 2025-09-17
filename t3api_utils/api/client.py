"""T3 API client built on httpx."""
from __future__ import annotations

from typing import Any, Dict, Optional, Union, cast

import httpx

from t3api_utils.api.interfaces import AuthResponseData, MetrcCollectionResponse
from t3api_utils.http.utils import (HTTPConfig, LoggingHooks, RetryPolicy,
                                    T3HTTPError, arequest_json,
                                    build_async_client, build_client,
                                    clear_bearer_token, request_json,
                                    set_bearer_token)


class T3APIClient:
    """T3 API client using httpx for HTTP requests.

    This client provides a high-level interface to the T3 API, handling
    authentication, retries, and response parsing.
    """

    def __init__(
        self,
        *,
        config: Optional[HTTPConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
        logging_hooks: Optional[LoggingHooks] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize the T3 API client.

        Args:
            config: HTTP configuration (host, timeout, etc.)
            retry_policy: Retry policy for failed requests
            logging_hooks: Optional request/response logging
            headers: Additional headers to include with requests
        """
        self._config = config or HTTPConfig()
        self._retry_policy = retry_policy or RetryPolicy()
        self._logging_hooks = logging_hooks
        self._extra_headers = headers or {}

        # Build the httpx client
        self._client = build_client(
            config=self._config,
            headers=self._extra_headers,
            hooks=self._logging_hooks,
        )

        # Track authentication state
        self._authenticated = False
        self._access_token: Optional[str] = None

    def __enter__(self) -> T3APIClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._authenticated and self._access_token is not None

    @property
    def access_token(self) -> Optional[str]:
        """Get the current access token."""
        return self._access_token

    def set_access_token(self, token: str) -> None:
        """Set the access token for authentication.

        Args:
            token: Bearer token for API authentication
        """
        self._access_token = token
        set_bearer_token(client=self._client, token=token)
        self._authenticated = True

    def clear_access_token(self) -> None:
        """Clear the access token."""
        self._access_token = None
        clear_bearer_token(client=self._client)
        self._authenticated = False

    def authenticate_with_credentials(
        self,
        *,
        hostname: str,
        username: str,
        password: str,
        otp: Optional[str] = None,
        email: Optional[str] = None,
    ) -> AuthResponseData:
        """Authenticate with T3 API using credentials.

        Args:
            hostname: The hostname for authentication
            username: Username
            password: Password
            otp: Optional one-time password
            email: Optional email address

        Returns:
            AuthResponseData containing access token and metadata

        Raises:
            T3HTTPError: If authentication fails
        """
        # Prepare request payload
        payload = {
            "hostname": hostname,
            "username": username,
            "password": password,
        }

        if otp is not None:
            payload["otp"] = otp

        if email is not None:
            payload["email"] = email

        # Make the request
        try:
            response_data = request_json(
                client=self._client,
                method="POST",
                url="/v2/auth/credentials",
                json_body=payload,
                policy=self._retry_policy,
                expected_status=200,
            )

            # Set the token for future requests
            self.set_access_token(response_data["accessToken"])

            return cast(AuthResponseData, response_data)

        except T3HTTPError as e:
            # Re-raise with more context
            raise T3HTTPError(f"Authentication failed: {e}", response=e.response) from e

    def get_licenses(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        **kwargs: Any,
    ) -> MetrcCollectionResponse:
        """Get licenses from the T3 API.

        Args:
            page: Page number (1-based)
            page_size: Number of items per page
            **kwargs: Additional query parameters

        Returns:
            MetrcCollectionResponse containing license data

        Raises:
            T3HTTPError: If request fails or user not authenticated
        """
        if not self.is_authenticated:
            raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

        # Prepare query parameters
        params = {
            "page": page,
            "pageSize": page_size,
            **kwargs,
        }

        try:
            response_data = request_json(
                client=self._client,
                method="GET",
                url="/v2/licenses",
                params=params,
                policy=self._retry_policy,
                expected_status=200,
            )

            return cast(MetrcCollectionResponse, response_data)

        except T3HTTPError as e:
            raise T3HTTPError(f"Failed to get licenses: {e}", response=e.response) from e

    def get_packages(
        self,
        *,
        license_number: str,
        page: int = 1,
        page_size: int = 100,
        **kwargs: Any,
    ) -> MetrcCollectionResponse:
        """Get packages for a specific license.

        Args:
            license_number: License number to get packages for
            page: Page number (1-based)
            page_size: Number of items per page
            **kwargs: Additional query parameters

        Returns:
            MetrcCollectionResponse containing package data

        Raises:
            T3HTTPError: If request fails or user not authenticated
        """
        if not self.is_authenticated:
            raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

        # Prepare query parameters
        params = {
            "licenseNumber": license_number,
            "page": page,
            "pageSize": page_size,
            **kwargs,
        }

        try:
            response_data = request_json(
                client=self._client,
                method="GET",
                url="/v2/packages",
                params=params,
                policy=self._retry_policy,
                expected_status=200,
            )

            return cast(MetrcCollectionResponse, response_data)

        except T3HTTPError as e:
            raise T3HTTPError(f"Failed to get packages: {e}", response=e.response) from e


class AsyncT3APIClient:
    """Async version of T3APIClient using httpx.AsyncClient.

    This client provides the same interface as T3APIClient but with async/await support
    for better performance when making many concurrent requests.
    """

    def __init__(
        self,
        *,
        config: Optional[HTTPConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
        logging_hooks: Optional[LoggingHooks] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize the async T3 API client.

        Args:
            config: HTTP configuration (host, timeout, etc.)
            retry_policy: Retry policy for failed requests
            logging_hooks: Optional request/response logging
            headers: Additional headers to include with requests
        """
        self._config = config or HTTPConfig()
        self._retry_policy = retry_policy or RetryPolicy()
        self._logging_hooks = logging_hooks
        self._extra_headers = headers or {}

        # Build the async httpx client
        self._client = build_async_client(
            config=self._config,
            headers=self._extra_headers,
            hooks=self._logging_hooks,
        )

        # Track authentication state
        self._authenticated = False
        self._access_token: Optional[str] = None

    async def __aenter__(self) -> AsyncT3APIClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._authenticated and self._access_token is not None

    @property
    def access_token(self) -> Optional[str]:
        """Get the current access token."""
        return self._access_token

    def set_access_token(self, token: str) -> None:
        """Set the access token for authentication.

        Args:
            token: Bearer token for API authentication
        """
        self._access_token = token
        set_bearer_token(client=self._client, token=token)
        self._authenticated = True

    def clear_access_token(self) -> None:
        """Clear the access token."""
        self._access_token = None
        clear_bearer_token(client=self._client)
        self._authenticated = False

    async def authenticate_with_credentials(
        self,
        *,
        hostname: str,
        username: str,
        password: str,
        otp: Optional[str] = None,
        email: Optional[str] = None,
    ) -> AuthResponseData:
        """Authenticate with T3 API using credentials.

        Args:
            hostname: The hostname for authentication
            username: Username
            password: Password
            otp: Optional one-time password
            email: Optional email address

        Returns:
            AuthResponseData containing access token and metadata

        Raises:
            T3HTTPError: If authentication fails
        """
        # Prepare request payload
        payload = {
            "hostname": hostname,
            "username": username,
            "password": password,
        }

        if otp is not None:
            payload["otp"] = otp

        if email is not None:
            payload["email"] = email

        # Make the request
        try:
            response_data = await arequest_json(
                aclient=self._client,
                method="POST",
                url="/v2/auth/credentials",
                json_body=payload,
                policy=self._retry_policy,
                expected_status=200,
            )

            # Set the token for future requests
            self.set_access_token(response_data["accessToken"])

            return cast(AuthResponseData, response_data)

        except T3HTTPError as e:
            # Re-raise with more context
            raise T3HTTPError(f"Authentication failed: {e}", response=e.response) from e

    async def get_licenses(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        **kwargs: Any,
    ) -> MetrcCollectionResponse:
        """Get licenses from the T3 API.

        Args:
            page: Page number (1-based)
            page_size: Number of items per page
            **kwargs: Additional query parameters

        Returns:
            MetrcCollectionResponse containing license data

        Raises:
            T3HTTPError: If request fails or user not authenticated
        """
        if not self.is_authenticated:
            raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

        # Prepare query parameters
        params = {
            "page": page,
            "pageSize": page_size,
            **kwargs,
        }

        try:
            response_data = await arequest_json(
                aclient=self._client,
                method="GET",
                url="/v2/licenses",
                params=params,
                policy=self._retry_policy,
                expected_status=200,
            )

            return cast(MetrcCollectionResponse, response_data)

        except T3HTTPError as e:
            raise T3HTTPError(f"Failed to get licenses: {e}", response=e.response) from e

    async def get_packages(
        self,
        *,
        license_number: str,
        page: int = 1,
        page_size: int = 100,
        **kwargs: Any,
    ) -> MetrcCollectionResponse:
        """Get packages for a specific license.

        Args:
            license_number: License number to get packages for
            page: Page number (1-based)
            page_size: Number of items per page
            **kwargs: Additional query parameters

        Returns:
            MetrcCollectionResponse containing package data

        Raises:
            T3HTTPError: If request fails or user not authenticated
        """
        if not self.is_authenticated:
            raise T3HTTPError("Client is not authenticated. Call authenticate_with_credentials() first.")

        # Prepare query parameters
        params = {
            "licenseNumber": license_number,
            "page": page,
            "pageSize": page_size,
            **kwargs,
        }

        try:
            response_data = await arequest_json(
                aclient=self._client,
                method="GET",
                url="/v2/packages",
                params=params,
                policy=self._retry_policy,
                expected_status=200,
            )

            return cast(MetrcCollectionResponse, response_data)

        except T3HTTPError as e:
            raise T3HTTPError(f"Failed to get packages: {e}", response=e.response) from e