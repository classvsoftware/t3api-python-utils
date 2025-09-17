"""Authentication utilities for T3 API using httpx-based client.

This module provides drop-in replacements for the t3api-based authentication
functions, maintaining the same interface while using our httpx implementation.
"""
from __future__ import annotations

from typing import Optional

from t3api_utils.api.client import T3APIClient
from t3api_utils.api.models import AuthResponseData
from t3api_utils.exceptions import AuthenticationError
from t3api_utils.http.utils import T3HTTPError, HTTPConfig


def create_credentials_authenticated_client_or_error(
    *,
    hostname: str,
    username: str,
    password: str,
    host: str = "https://api.trackandtrace.tools",
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> T3APIClient:
    """
    Authenticates with the T3 API using credentials and returns an authenticated client.

    This function replaces the t3api-based authentication function with the same
    signature, providing a drop-in replacement.

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
    try:
        # Create HTTP config with the specified host
        config = HTTPConfig(host=host)

        # Create and authenticate the client
        client = T3APIClient(config=config)

        auth_response = client.authenticate_with_credentials(
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


def authenticate_and_get_token(
    *,
    hostname: str,
    username: str,
    password: str,
    host: str = "https://api.trackandtrace.tools",
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """
    Authenticate and return just the access token.

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
    client = create_credentials_authenticated_client_or_error(
        hostname=hostname,
        username=username,
        password=password,
        host=host,
        otp=otp,
        email=email,
    )

    if client.access_token is None:
        raise AuthenticationError("Authentication succeeded but no access token was returned")

    return client.access_token


def authenticate_and_get_response(
    *,
    hostname: str,
    username: str,
    password: str,
    host: str = "https://api.trackandtrace.tools",
    otp: Optional[str] = None,
    email: Optional[str] = None,
) -> AuthResponseData:
    """
    Authenticate and return the full authentication response.

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
        # Create HTTP config with the specified host
        config = HTTPConfig(host=host)

        # Create client and authenticate
        with T3APIClient(config=config) as client:
            auth_response = client.authenticate_with_credentials(
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