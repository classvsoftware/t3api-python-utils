#!/usr/bin/env python3
"""Example demonstrating the new generic get_data function."""

from t3api_utils.api.operations import get_data, get_data_async, get_collection
from t3api_utils.main.utils import get_authenticated_client_or_error

def main():
    """Demonstrate the generic get_data function."""
    # Get authenticated client
    client = get_authenticated_client_or_error()

    # Example 1: Get licenses (same as get_collection but more flexible)
    print("=== Example 1: Get licenses with custom params ===")
    licenses = get_data(
        client,
        "/v2/licenses",
        params={
            "page": 1,
            "pageSize": 5,
            "state": "CA"  # Custom parameter
        }
    )
    print(f"Found {len(licenses.get('data', []))} licenses")

    # Example 1b: Using get_collection with new T3 API parameters
    print("=== Example 1b: Get packages using get_collection with T3 API params ===")
    try:
        packages = get_collection(
            client,
            "/v2/packages",
            license_number="LIC-001",  # Required for most endpoints
            page=1,
            page_size=10,
            sort="label:asc",
            filter=["label__endswith:0003"],
            filter_logic="and",
            strict_pagination=True
        )
        print(f"Found {len(packages.get('data', []))} packages")
    except Exception as e:
        print(f"Error (expected for demo): {e}")

    # Example 2: Get a specific facility (single resource, not collection)
    # This demonstrates the flexibility - get_collection assumes pagination
    print("\n=== Example 2: Get specific facility (single resource) ===")
    try:
        # This would fail with get_collection since it assumes pagination params
        facility_data = get_data(
            client,
            "/v2/facilities/1",  # Specific facility ID
            expected_status=(200, 404)  # Allow both success and not found
        )
        print(f"Facility data: {facility_data}")
    except Exception as e:
        print(f"Error (expected for demo): {e}")

    # Example 3: POST request (get_collection only does GET)
    print("\n=== Example 3: POST request capability ===")
    try:
        # This demonstrates POST capability (not possible with get_collection)
        post_result = get_data(
            client,
            "/v2/some-action",
            method="POST",
            json_body={"action": "test"},
            expected_status=(200, 201, 400)  # Allow various statuses
        )
        print(f"POST result: {post_result}")
    except Exception as e:
        print(f"POST error (expected for demo): {e}")

if __name__ == "__main__":
    main()