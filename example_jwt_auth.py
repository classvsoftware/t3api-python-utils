#!/usr/bin/env python3
"""Example demonstrating JWT token authentication."""

from t3api_utils.main.utils import get_jwt_authenticated_client_or_error
from t3api_utils.auth.utils import create_jwt_authenticated_client
from t3api_utils.api.operations import get_data
from t3api_utils.style import print_error, print_header, print_info, print_subheader, print_success


def main():
    """Demonstrate JWT authentication methods."""
    # Replace with your actual JWT token
    jwt_token = "your_jwt_token_here"

    print_header("JWT Authentication Examples")

    # Method 1: Using the high-level main utils function
    print_subheader("1. Using get_jwt_authenticated_client_or_error()")
    try:
        client = get_jwt_authenticated_client_or_error(jwt_token)
        print_success("Successfully created authenticated client using main utils")

        # Test the client by fetching licenses
        licenses_response = get_data(client, "/v2/licenses")
        print_success(f"Found {len(licenses_response.get('data', []))} licenses")

    except Exception as e:
        print_error(f"Error: {e}")

    # Method 2: Using the lower-level auth utils function
    print_subheader("2. Using create_jwt_authenticated_client()")
    try:
        client = create_jwt_authenticated_client(jwt_token)
        print_success("Successfully created authenticated client using auth utils")

        # Test the client by fetching licenses
        licenses_response = get_data(client, "/v2/licenses")
        print_success(f"Found {len(licenses_response.get('data', []))} licenses")

    except Exception as e:
        print_error(f"Error: {e}")

    # Method 3: Using custom configuration
    print_subheader("3. Using JWT authentication with custom configuration")
    try:
        from t3api_utils.http.utils import HTTPConfig

        # Create custom config for staging environment
        custom_config = HTTPConfig(
            host="https://api.staging.trackandtrace.tools",
            timeout=60.0
        )

        client = create_jwt_authenticated_client(
            jwt_token,
            config=custom_config
        )
        print_success("Successfully created client with custom config")

    except Exception as e:
        print_error(f"Error: {e}")


if __name__ == "__main__":
    main()