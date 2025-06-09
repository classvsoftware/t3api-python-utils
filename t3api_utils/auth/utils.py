from typing import Optional

import certifi
from t3api import (ApiClient, AuthenticationApi, Configuration,
                   V2AuthCredentialsPostRequest)
from t3api.exceptions import ApiException

from t3api_utils.exceptions import \
    AuthenticationError  # ← now imported from your module


def create_credentials_authenticated_client_or_error(
    *,
    hostname: str,
    username: str,
    password: str,
    host: str = "https://api.trackandtrace.tools",
    otp: Optional[str] = None,
) -> ApiClient:
    """
    Authenticates with the T3 API using credentials and optional OTP.

    Returns:
        ApiClient: An authenticated client instance.

    Raises:
        AuthenticationError: If authentication fails.
    """
    config = Configuration(host=host)
    config.ssl_ca_cert = certifi.where()

    client = ApiClient(configuration=config)
    auth_api = AuthenticationApi(api_client=client)

    request_data_args = {
        "hostname": hostname,
        "username": username,
        "password": password,
    }

    # Only send OTP if it is needed, otherwise omit
    if otp is not None:
        request_data_args["otp"] = otp

    request_data = V2AuthCredentialsPostRequest(**request_data_args)
    try:
        response = auth_api.v2_auth_credentials_post(request_data)
        config.access_token = response.access_token
        return client

    except ApiException as e:
        raise AuthenticationError(f"T3 API authentication failed: {e.body}") from e
    except Exception as e:
        raise AuthenticationError(f"Unexpected authentication error: {str(e)}") from e
