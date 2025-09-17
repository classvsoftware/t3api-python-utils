"""Authentication utilities for T3 API using httpx-based client."""
from typing import Optional

from t3api_utils.api.auth import create_credentials_authenticated_client_or_error as _httpx_auth_client
from t3api_utils.api.client import T3APIClient


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
