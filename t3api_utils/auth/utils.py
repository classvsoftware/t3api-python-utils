"""Authentication utilities for T3 API using httpx-based client.

This module provides authentication functions using our async httpx implementation
with sync wrappers for compatibility.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.interfaces import AuthResponseData
from t3api_utils.cli.utils import config_manager
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.http.utils import T3HTTPError, HTTPConfig, RetryPolicy, LoggingHooks


async def create_credentials_authenticated_client_or_error_async(
    *,
    hostname: str,
    username: str,
    password: str,
    host: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> T3APIClient:
    """
    Authenticates with the T3 API using credentials and returns an authenticated client (async).

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        T3APIClient: An authenticated async client instance ready for use

    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        # Create HTTP config with host from config or parameter
        effective_host = host or config_manager.get_api_host()
        config = HTTPConfig(host=effective_host)

        # Create and authenticate the client
        client = T3APIClient(config=config)

        await client.authenticate_with_credentials(
            hostname=hostname,
            username=username,
            password=password,
            otp=otp,
            email=email,
        )

        return client

    except T3HTTPError as e:
        raise AuthenticationError(f"T3 API authentication failed: {e}") from e
    except Exception as e:
        raise AuthenticationError(f"Unexpected authentication error: {str(e)}") from e


def create_credentials_authenticated_client_or_error(
    *,
    hostname: str,
    username: str,
    password: str,
    host: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> T3APIClient:
    """
    Authenticates with the T3 API using credentials and returns an authenticated client (sync wrapper).

    This function provides a sync wrapper around the async implementation.

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        T3APIClient: An authenticated client instance ready for use

    Raises:
        AuthenticationError: If authentication fails
    """
    return asyncio.run(create_credentials_authenticated_client_or_error_async(
        hostname=hostname,
        username=username,
        password=password,
        host=host,
        otp=otp,
        email=email,
    ))


async def authenticate_and_get_token_async(
    *,
    hostname: str,
    username: str,
    password: str,
    host: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """
    Authenticate and return just the access token (async).

    This is a convenience function for when you only need the token
    and not the full client.

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        str: The access token

    Raises:
        AuthenticationError: If authentication fails
    """
    client = await create_credentials_authenticated_client_or_error_async(
        hostname=hostname,
        username=username,
        password=password,
        host=host,
        otp=otp,
        email=email,
    )

    if client.access_token is None:
        raise AuthenticationError("Authentication succeeded but no access token was returned")

    # Clean up the client
    await client.close()

    return client.access_token


def authenticate_and_get_token(
    *,
    hostname: str,
    username: str,
    password: str,
    host: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """
    Authenticate and return just the access token (sync wrapper).

    This is a convenience function for when you only need the token
    and not the full client.

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        str: The access token

    Raises:
        AuthenticationError: If authentication fails
    """
    return asyncio.run(authenticate_and_get_token_async(
        hostname=hostname,
        username=username,
        password=password,
        host=host,
        otp=otp,
        email=email,
    ))


async def authenticate_and_get_response_async(
    *,
    hostname: str,
    username: str,
    password: str,
    host: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> AuthResponseData:
    """
    Authenticate and return the full authentication response (async).

    This function provides access to all authentication response data
    including refresh tokens and expiration information.

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        AuthResponseData: The complete authentication response

    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        # Create HTTP config with host from config or parameter
        effective_host = host or config_manager.get_api_host()
        config = HTTPConfig(host=effective_host)

        # Create client and authenticate
        async with T3APIClient(config=config) as client:
            auth_response = await client.authenticate_with_credentials(
                hostname=hostname,
                username=username,
                password=password,
                otp=otp,
                email=email,
            )

            return auth_response

    except T3HTTPError as e:
        raise AuthenticationError(f"T3 API authentication failed: {e}") from e
    except Exception as e:
        raise AuthenticationError(f"Unexpected authentication error: {str(e)}") from e


def authenticate_and_get_response(
    *,
    hostname: str,
    username: str,
    password: str,
    host: Optional[str] = None,
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> AuthResponseData:
    """
    Authenticate and return the full authentication response (sync wrapper).

    This function provides access to all authentication response data
    including refresh tokens and expiration information.

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        AuthResponseData: The complete authentication response

    Raises:
        AuthenticationError: If authentication fails
    """
    return asyncio.run(authenticate_and_get_response_async(
        hostname=hostname,
        username=username,
        password=password,
        host=host,
        otp=otp,
        email=email,
    ))


def create_jwt_authenticated_client(
    *,
    jwt_token: str,
    host: Optional[str] = None,
    config: Optional[HTTPConfig] = None,
    retry_policy: Optional[RetryPolicy] = None,
    logging_hooks: Optional[LoggingHooks] = None,
    headers: Optional[Dict[str, str]] = None,
) -> T3APIClient:
    """
    Creates an authenticated T3 API client using a pre-existing JWT token.

    This function allows users to directly provide their JWT token instead of
    going through the username/password authentication flow.

    Args:
        jwt_token: Valid JWT access token for the T3 API
        host: API host URL (optional, defaults to production if no config provided)
        config: Optional HTTP configuration (timeout, etc.)
        retry_policy: Optional retry policy for failed requests
        logging_hooks: Optional request/response logging hooks
        headers: Optional additional headers to include with requests

    Returns:
        T3APIClient: An authenticated async client instance

    Raises:
        ValueError: If jwt_token is empty or None

    Example:
        >>> token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        >>> client = create_jwt_authenticated_client(jwt_token=token)
        >>> # Client is ready to use for API calls (note: it's async)
    """
    if not jwt_token or not jwt_token.strip():
        raise ValueError("JWT token cannot be empty or None")

    # Handle host and config parameters
    if config is None:
        # No config provided, create one with specified host or default
        effective_host = host or config_manager.get_api_host()
        config = HTTPConfig(host=effective_host)
    elif host is not None and config.host != host:
        # Config provided but different host explicitly specified
        config = HTTPConfig(
            host=host,
            timeout=config.timeout,
            verify_ssl=config.verify_ssl,
            base_headers=config.base_headers,
            proxies=config.proxies,
        )
    # Otherwise, use the provided config as-is

    # Create the client
    client = T3APIClient(
        config=config,
        retry_policy=retry_policy,
        logging_hooks=logging_hooks,
        headers=headers,
    )

    # Set the JWT token
    client.set_access_token(jwt_token.strip())

    return client


def create_api_key_authenticated_client(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
    config: Optional[HTTPConfig] = None,
    retry_policy: Optional[RetryPolicy] = None,
    logging_hooks: Optional[LoggingHooks] = None,
    headers: Optional[Dict[str, str]] = None,
) -> T3APIClient:
    """
    Creates an authenticated T3 API client using an API key.

    This function provides API key authentication by calling the /v2/auth/apikey
    endpoint with the provided API key and state code.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production if no config provided)
        config: Optional HTTP configuration (timeout, etc.)
        retry_policy: Optional retry policy for failed requests
        logging_hooks: Optional request/response logging hooks
        headers: Optional additional headers to include with requests

    Returns:
        T3APIClient: An authenticated async client instance

    Raises:
        ValueError: If api_key or state_code is empty or None
        AuthenticationError: If API key authentication fails

    Example:
        >>> client = create_api_key_authenticated_client(
        ...     api_key="your-api-key",
        ...     state_code="CA"
        ... )
        >>> # Client is ready to use for API calls (note: it's async)
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key cannot be empty or None")

    if not state_code or not state_code.strip():
        raise ValueError("State code cannot be empty or None")

    # Handle host and config parameters
    if config is None:
        # No config provided, create one with specified host or default
        effective_host = host or config_manager.get_api_host()
        config = HTTPConfig(host=effective_host)
    elif host is not None and config.host != host:
        # Config provided but different host explicitly specified
        config = HTTPConfig(
            host=host,
            timeout=config.timeout,
            verify_ssl=config.verify_ssl,
            base_headers=config.base_headers,
            proxies=config.proxies,
        )
    # Otherwise, use the provided config as-is

    # Create the client
    client = T3APIClient(
        config=config,
        retry_policy=retry_policy,
        logging_hooks=logging_hooks,
        headers=headers,
    )

    # Note: This function creates the client but doesn't authenticate it yet
    # The caller needs to call authenticate_with_api_key() or use the high-level functions
    return client


async def create_api_key_authenticated_client_or_error_async(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
) -> T3APIClient:
    """
    Authenticates with the T3 API using API key and returns an authenticated client (async).

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production)

    Returns:
        T3APIClient: An authenticated async client instance ready for use

    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        # Create HTTP config with host from config or parameter
        effective_host = host or config_manager.get_api_host()
        config = HTTPConfig(host=effective_host)

        # Create and authenticate the client
        client = T3APIClient(config=config)

        await client.authenticate_with_api_key(
            api_key=api_key,
            state_code=state_code,
        )

        return client

    except T3HTTPError as e:
        raise AuthenticationError(f"T3 API key authentication failed: {e}") from e
    except Exception as e:
        raise AuthenticationError(f"Unexpected API key authentication error: {str(e)}") from e


def create_api_key_authenticated_client_or_error(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
) -> T3APIClient:
    """
    Authenticates with the T3 API using API key and returns an authenticated client (sync wrapper).

    This function provides a sync wrapper around the async implementation.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production)

    Returns:
        T3APIClient: An authenticated client instance ready for use

    Raises:
        AuthenticationError: If authentication fails
    """
    return asyncio.run(create_api_key_authenticated_client_or_error_async(
        api_key=api_key,
        state_code=state_code,
        host=host,
    ))


async def authenticate_and_get_token_with_api_key_async(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
) -> str:
    """
    Authenticate with API key and return just the access token (async).

    This is a convenience function for when you only need the token
    and not the full client.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production)

    Returns:
        str: The access token

    Raises:
        AuthenticationError: If authentication fails
    """
    client = await create_api_key_authenticated_client_or_error_async(
        api_key=api_key,
        state_code=state_code,
        host=host,
    )

    if client.access_token is None:
        raise AuthenticationError("API key authentication succeeded but no access token was returned")

    # Clean up the client
    await client.close()

    return client.access_token


def authenticate_and_get_token_with_api_key(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
) -> str:
    """
    Authenticate with API key and return just the access token (sync wrapper).

    This is a convenience function for when you only need the token
    and not the full client.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production)

    Returns:
        str: The access token

    Raises:
        AuthenticationError: If authentication fails
    """
    return asyncio.run(authenticate_and_get_token_with_api_key_async(
        api_key=api_key,
        state_code=state_code,
        host=host,
    ))


async def authenticate_and_get_response_with_api_key_async(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
) -> AuthResponseData:
    """
    Authenticate with API key and return the full authentication response (async).

    This function provides access to all authentication response data
    including refresh tokens and expiration information.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production)

    Returns:
        AuthResponseData: The complete authentication response

    Raises:
        AuthenticationError: If authentication fails
    """
    try:
        # Create HTTP config with host from config or parameter
        effective_host = host or config_manager.get_api_host()
        config = HTTPConfig(host=effective_host)

        # Create client and authenticate
        async with T3APIClient(config=config) as client:
            auth_response = await client.authenticate_with_api_key(
                api_key=api_key,
                state_code=state_code,
            )

            return auth_response

    except T3HTTPError as e:
        raise AuthenticationError(f"T3 API key authentication failed: {e}") from e
    except Exception as e:
        raise AuthenticationError(f"Unexpected API key authentication error: {str(e)}") from e


def authenticate_and_get_response_with_api_key(
    *,
    api_key: str,
    state_code: str,
    host: Optional[str] = None,
) -> AuthResponseData:
    """
    Authenticate with API key and return the full authentication response (sync wrapper).

    This function provides access to all authentication response data
    including refresh tokens and expiration information.

    Args:
        api_key: API key for the T3 API
        state_code: State code (e.g., "CA", "MO", "CO", "MI")
        host: API host URL (optional, defaults to production)

    Returns:
        AuthResponseData: The complete authentication response

    Raises:
        AuthenticationError: If authentication fails
    """
    return asyncio.run(authenticate_and_get_response_with_api_key_async(
        api_key=api_key,
        state_code=state_code,
        host=host,
    ))
