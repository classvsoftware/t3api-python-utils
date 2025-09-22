"""OpenAPI specification fetcher and parser for T3 API collections."""

import sys
from typing import Any, Dict, List, TypedDict

import httpx

from t3api_utils.style import console


class CollectionEndpoint(TypedDict):
    """Type definition for a collection endpoint."""
    path: str
    method: str
    name: str
    category: str
    description: str


def fetch_openapi_spec() -> Dict[str, Any]:
    """
    Fetch the OpenAPI specification from the live T3 API.

    Returns:
        The parsed OpenAPI specification as a dictionary.

    Raises:
        SystemExit: If the API cannot be reached or returns invalid data.
    """
    spec_url = "https://api.trackandtrace.tools/v2/spec/openapi.json"

    console.print(f"Fetching OpenAPI spec from {spec_url}...")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(spec_url)
            response.raise_for_status()

        spec: Dict[str, Any] = response.json()
        console.print("✓ OpenAPI spec fetched successfully")
        return spec

    except httpx.HTTPError as e:
        console.print(f"✗ Failed to fetch OpenAPI spec: {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"✗ Error parsing OpenAPI spec: {e}")
        sys.exit(1)


def parse_collection_endpoints(spec: Dict[str, Any]) -> List[CollectionEndpoint]:
    """
    Parse collection endpoints from OpenAPI spec.

    Args:
        spec: The OpenAPI specification dictionary.

    Returns:
        List of collection endpoints with metadata.

    Raises:
        SystemExit: If no collection endpoints are found.
    """
    collection_endpoints: List[CollectionEndpoint] = []

    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue

            tags = operation.get("tags", [])
            summary = operation.get("summary", "")

            # Look for collection-like endpoints based on common patterns
            if not _is_collection_endpoint(path, method, tags, summary):
                continue

            # Extract endpoint metadata
            description = operation.get("description", summary) or summary

            # Determine category from path or tags
            category = _determine_category(path, tags)

            # Create display name from summary or path
            name = _create_display_name(summary, path)

            endpoint = CollectionEndpoint(
                path=path,
                method=method.upper(),
                name=name,
                category=category,
                description=description
            )

            collection_endpoints.append(endpoint)

    if not collection_endpoints:
        console.print("✗ No collection endpoints found in OpenAPI spec")
        sys.exit(1)

    console.print(f"✓ Found {len(collection_endpoints)} collection endpoints")
    return collection_endpoints


def _determine_category(path: str, tags: List[str]) -> str:
    """Determine the category for an endpoint based on path and tags."""
    # Remove Collection tag and use remaining tags
    other_tags = [tag for tag in tags if tag != "Collection"]
    if other_tags:
        return other_tags[0]

    # Fallback to path-based categorization
    path_parts = path.strip("/").split("/")
    if len(path_parts) >= 2:
        return path_parts[1].title()  # e.g., "packages" -> "Packages"

    return "General"


def _create_display_name(summary: str, path: str) -> str:
    """Create a user-friendly display name for the endpoint."""
    if summary:
        return summary

    # Fallback: create name from path
    path_parts = path.strip("/").split("/")
    if len(path_parts) >= 2:
        name_parts = path_parts[1:]
        return " ".join(part.replace("-", " ").title() for part in name_parts)

    return path


def _is_collection_endpoint(path: str, method: str, tags: List[str], summary: str) -> bool:
    """
    Determine if an endpoint represents a collection of data.

    Based on the API analysis, collection endpoints are typically:
    - GET requests that return lists
    - Main resource endpoints (not single item details)
    - Tagged with primary resource names
    """
    # Only consider GET requests for collections
    if method.lower() != "get":
        return False

    # Skip single item endpoints (endpoints that operate on a single resource)
    single_item_indicators = [
        "/history", "/photos", "/file", "/manifest", "/transactions",
        "/deliveries", "/transporter-details", "/labresults", "/document",
        "/source-harvests", "/required-labtest-batches", "/labresult-batches",
        "/source-packages"
    ]

    if any(indicator in path for indicator in single_item_indicators):
        return False

    # Skip report endpoints
    if "/report" in path or "report" in summary.lower():
        return False

    # Skip create/modify/auth endpoints
    skip_tags = [
        "Create Package", "Create Strains", "Create Transfer", "Modify Items",
        "Modify Packages", "Modify Sales Receipts", "Modify Strains",
        "Modify Transfer", "Modify Transfer Template", "Authentication",
        "Files", "PDF", "Photos", "Permissions", "Labels", "Search"
    ]

    if any(tag in skip_tags for tag in tags):
        return False

    # Include main collection tags
    collection_tags = [
        "Packages", "Items", "Harvests", "Plants", "Plant Batches",
        "Sales Receipts", "Transfers", "Transfer Templates", "Strains",
        "Tags", "Locations", "Licenses", "States", "Supercollections"
    ]

    # Check if any of the tags are collection tags
    return any(tag in collection_tags for tag in tags)


def get_collection_endpoints() -> List[CollectionEndpoint]:
    """
    Fetch and parse collection endpoints from the live API.

    Returns:
        List of available collection endpoints.
    """
    spec = fetch_openapi_spec()
    return parse_collection_endpoints(spec)