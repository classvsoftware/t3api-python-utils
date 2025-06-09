from t3api_utils.auth.utils import create_credentials_authenticated_client
from t3api_utils.cli.utils import resolve_auth_inputs_or_error


def get_authenticated_client():
    """
    High-level method to return an authenticated client.
    Handles CLI prompts, .env, and validation internally.
    """
    inputs = resolve_auth_inputs_or_error()
    return create_credentials_authenticated_client(**inputs)
