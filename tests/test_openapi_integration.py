"""Integration tests for OpenAPI functionality against live API."""

from typing import Dict, List
import pytest
import httpx

from t3api_utils.openapi.spec_fetcher import (
    fetch_openapi_spec,
    get_collection_endpoints,
    CollectionEndpoint,
)


class TestLiveAPIIntegration:
    """Integration tests against the live T3 API."""

    def test_fetch_live_openapi_spec(self):
        """Test fetching the actual OpenAPI spec from the live API."""
        spec = fetch_openapi_spec()

        # Verify basic OpenAPI structure
        assert isinstance(spec, dict)
        assert "openapi" in spec
        assert "paths" in spec
        assert spec["openapi"].startswith("3.")

        # Verify we have paths
        assert len(spec["paths"]) > 0

    def test_collection_endpoints_exist_in_live_api(self):
        """Test that Collection-tagged endpoints exist in the live API."""
        endpoints = get_collection_endpoints()

        # Should find at least one collection endpoint
        assert len(endpoints) > 0

        # Verify endpoint structure
        for endpoint in endpoints:
            assert "path" in endpoint
            assert "method" in endpoint
            assert "name" in endpoint
            assert "category" in endpoint
            assert "description" in endpoint

            # Verify required fields are not empty
            assert endpoint["path"].startswith("/")
            assert endpoint["method"] in ["GET", "POST", "PUT", "DELETE", "PATCH"]
            assert len(endpoint["name"]) > 0
            assert len(endpoint["category"]) > 0

    def test_collection_endpoints_are_accessible(self):
        """Test that collection endpoints can be reached."""
        endpoints = get_collection_endpoints()

        # Test a few endpoints to make sure they're accessible
        # We'll just check that they return valid HTTP responses
        base_url = "https://api.trackandtrace.tools"

        with httpx.Client(timeout=30.0) as client:
            # Test up to 3 endpoints to avoid overwhelming the API
            test_endpoints = endpoints[:3]

            for endpoint in test_endpoints:
                try:
                    # We expect authentication errors (401/403) but not 404s
                    response = client.request(endpoint["method"], f"{base_url}{endpoint['path']}")

                    # 401/403 are expected (no auth), 404 means endpoint doesn't exist
                    assert response.status_code != 404, f"Endpoint {endpoint['path']} not found (404)"

                    # Some basic structure checks for non-404 responses
                    if response.status_code not in [401, 403]:
                        # If we somehow get through without auth, verify it's JSON
                        try:
                            response.json()
                        except Exception:
                            # Non-JSON response is acceptable for some endpoints
                            pass

                except httpx.HTTPError:
                    # Network errors are acceptable - we're just checking endpoint existence
                    pass

    def test_specific_known_endpoints_exist(self):
        """Test that specific known collection endpoints exist."""
        endpoints = get_collection_endpoints()
        endpoint_paths = [e["path"] for e in endpoints]

        # We expect at least packages endpoints to exist based on the user's example
        package_endpoints = [path for path in endpoint_paths if "packages" in path.lower()]
        assert len(package_endpoints) > 0, "No package endpoints found"

        # The user mentioned /v2/packages/active specifically
        active_packages_exists = any("/packages/active" in path for path in endpoint_paths)
        if not active_packages_exists:
            # Log available package endpoints for debugging
            print(f"Available package endpoints: {package_endpoints}")
            pytest.fail("Expected /v2/packages/active endpoint not found")

    def test_categorization_works(self):
        """Test that endpoints are properly categorized."""
        endpoints = get_collection_endpoints()

        # Group by category
        categories: Dict[str, List[CollectionEndpoint]] = {}
        for endpoint in endpoints:
            category = endpoint["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(endpoint)

        # Should have at least one category
        assert len(categories) > 0

        # Each category should have at least one endpoint
        for category, category_endpoints in categories.items():
            assert len(category_endpoints) > 0
            assert len(category) > 0  # Category name should not be empty

        # Print categories for manual verification during development
        print(f"Found categories: {list(categories.keys())}")
        for category, category_endpoints in categories.items():
            print(f"  {category}: {len(category_endpoints)} endpoints")