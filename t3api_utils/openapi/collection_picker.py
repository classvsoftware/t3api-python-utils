"""Collection picker interface for selecting T3 API endpoints."""

import sys
from typing import Dict, List

import typer
from rich.table import Table

from t3api_utils.style import console
from .spec_fetcher import CollectionEndpoint, get_collection_endpoints


def pick_collection() -> CollectionEndpoint:
    """
    Interactive picker for selecting a collection endpoint.

    Returns:
        The selected collection endpoint.

    Raises:
        SystemExit: If user cancels or no endpoints are available.
    """
    endpoints = get_collection_endpoints()

    # Group endpoints by category
    categories = _group_by_category(endpoints)

    if len(categories) == 1:
        # If only one category, show endpoints directly
        category_name = list(categories.keys())[0]
        return _pick_from_category(category_name, categories[category_name])
    else:
        # Multiple categories, let user pick category first
        selected_category = _pick_category(categories)
        return _pick_from_category(selected_category, categories[selected_category])


def _group_by_category(endpoints: List[CollectionEndpoint]) -> Dict[str, List[CollectionEndpoint]]:
    """Group endpoints by their category."""
    categories: Dict[str, List[CollectionEndpoint]] = {}

    for endpoint in endpoints:
        category = endpoint["category"]
        if category not in categories:
            categories[category] = []
        categories[category].append(endpoint)

    # Sort endpoints within each category by name
    for category_endpoints in categories.values():
        category_endpoints.sort(key=lambda e: e["name"])

    return categories


def _pick_category(categories: Dict[str, List[CollectionEndpoint]]) -> str:
    """Let user pick a category."""
    category_list = sorted(categories.keys())

    table = Table(title="Available Collection Categories", border_style="magenta", header_style="bold magenta")
    table.add_column("#", style="magenta", justify="right")
    table.add_column("Category", style="bright_white")
    table.add_column("Endpoints", style="cyan")

    for i, category in enumerate(category_list, 1):
        endpoint_count = len(categories[category])
        table.add_row(str(i), category, str(endpoint_count))

    console.print(table)

    while True:
        try:
            choice = typer.prompt("Select category (number)", show_default=False)
            choice_int = int(choice)

            if 1 <= choice_int <= len(category_list):
                selected_category = category_list[choice_int - 1]
                console.print(f"Selected category: {selected_category}")
                return selected_category
            else:
                console.print(f"Please enter a number between 1 and {len(category_list)}")

        except (ValueError, typer.Abort):
            console.print("Selection cancelled")
            sys.exit(0)
        except KeyboardInterrupt:
            console.print("\nSelection cancelled")
            sys.exit(0)


def _pick_from_category(category_name: str, endpoints: List[CollectionEndpoint]) -> CollectionEndpoint:
    """Let user pick an endpoint from a category."""
    table = Table(title=f"Available {category_name} Collections", border_style="magenta", header_style="bold magenta")
    table.add_column("#", style="magenta", justify="right")
    table.add_column("Collection Name", style="bright_white")
    table.add_column("Endpoint", style="cyan")

    for i, endpoint in enumerate(endpoints, 1):
        endpoint_path = f"{endpoint['method']} {endpoint['path']}"
        table.add_row(str(i), endpoint['name'], endpoint_path)

    console.print(table)

    while True:
        try:
            choice = typer.prompt("Select collection (number)", show_default=False)
            choice_int = int(choice)

            if 1 <= choice_int <= len(endpoints):
                selected_endpoint = endpoints[choice_int - 1]
                console.print(f"Selected: {selected_endpoint['name']}")
                console.print(f"Endpoint: {selected_endpoint['method']} {selected_endpoint['path']}")
                return selected_endpoint
            else:
                console.print(f"Please enter a number between 1 and {len(endpoints)}")

        except (ValueError, typer.Abort):
            console.print("Selection cancelled")
            sys.exit(0)
        except KeyboardInterrupt:
            console.print("\nSelection cancelled")
            sys.exit(0)