from t3api import ApiClient

from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.auth.utils import \
    create_credentials_authenticated_client_or_error
from t3api_utils.cli.utils import resolve_auth_inputs_or_error


def get_authenticated_client() -> ApiClient:
    """
    High-level method to return an authenticated client.
    Handles CLI prompts, .env, and validation internally.
    """
    inputs: T3Credentials = resolve_auth_inputs_or_error()
    return create_credentials_authenticated_client_or_error(**inputs)
