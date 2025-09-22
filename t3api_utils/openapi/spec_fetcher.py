"""OpenAPI specification fetcher and parser for T3 API collections."""

import sys
from typing import Any, Dict, List, TypedDict

import httpx

from t3api_utils.cli.utils import config_manager
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
    api_host = config_manager.get_api_host()
    spec_url = f"{api_host}/v2/spec/openapi.json"

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

            # Look for collection endpoints based on pagination support
            if not _is_collection_endpoint(operation, path):
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


def _is_collection_endpoint(operation: Dict[str, Any], path: str) -> bool:
    """
    Determine if an endpoint represents a collection of data.

    Collection endpoints are identified by having a 'page' parameter,
    which indicates they support pagination and return lists of items.

    We also filter out single-item detail endpoints to focus on
    main collections that users would want to load entirely.
    """
    # Check if the operation has parameters
    parameters = operation.get("parameters", [])

    # Look for a 'page' parameter
    has_page_param = False
    for param in parameters:
        if isinstance(param, dict) and param.get("name") == "page":
            has_page_param = True
            break

    if not has_page_param:
        return False

    # Check if this requires a specific ID parameter (single-item endpoints)
    # These endpoints operate on a specific resource rather than collections
    id_parameters = [
        "itemId", "packageId", "transferId", "harvestId", "plantId",
        "plantBatchId", "salesId", "deliveryId", "labTestResultDocumentFileId"
    ]

    for param in parameters:
        if isinstance(param, dict) and param.get("name") in id_parameters:
            return False

    # Also exclude report endpoints (they don't return JSON collections)
    if "/report" in path:
        return False

    # Exclude create helper endpoints
    if "/create/" in path:
        return False

    return True


def get_collection_endpoints() -> List[CollectionEndpoint]:
    """
    Fetch and parse collection endpoints from the live API.

    Returns:
        List of available collection endpoints.
    """
    spec = fetch_openapi_spec()
    return parse_collection_endpoints(spec)