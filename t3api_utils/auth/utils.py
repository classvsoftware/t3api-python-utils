"""Authentication utilities for T3 API using httpx-based client."""
from typing import Dict, Optional

from t3api_utils.api.auth import create_credentials_authenticated_client_or_error as _httpx_auth_client
from t3api_utils.api.client import T3APIClient
from t3api_utils.http.utils import HTTPConfig, RetryPolicy, LoggingHooks


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
    Authenticates with the T3 API using credentials and optional OTP.

    Args:
        hostname: The hostname for authentication
        username: Username
        password: Password
        host: API host URL (defaults to production)
        otp: Optional one-time password
        email: Optional email address

    Returns:
        T3APIClient: An authenticated httpx-based client instance

    Raises:
        AuthenticationError: If authentication fails
    """
    return _httpx_auth_client(
        hostname=hostname,
        username=username,
        password=password,
        host=host,
        otp=otp,
        email=email,
    )


def create_jwt_authenticated_client(
    jwt_token: str,
    *,
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
        T3APIClient: An authenticated httpx-based client instance

    Raises:
        ValueError: If jwt_token is empty or None

    Example:
        >>> token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        >>> client = create_jwt_authenticated_client(token)
        >>> # Client is ready to use for API calls
    """
    if not jwt_token or not jwt_token.strip():
        raise ValueError("JWT token cannot be empty or None")

    # Handle host and config parameters
    if config is None:
        # No config provided, create one with specified host or default
        effective_host = host or "https://api.trackandtrace.tools"
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
