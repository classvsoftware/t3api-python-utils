#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "duckdb",
#     "httpx",
#     "typer",
#     "rich",
#     "pyarrow"
# ]
# ///

from typing import Any, Dict, List

from t3api_utils.api.parallel import load_all_data_sync
from t3api_utils.main.utils import (
    get_authenticated_client_or_error,
    interactive_collection_handler,
    pick_license,
)
from t3api_utils.style import print_warning


def main():
    # Get authenticated httpx-based client
    api_client = get_authenticated_client_or_error()

    # Pick a license interactively
    license = pick_license(api_client=api_client)

    # Load all packages for the selected license using the new parallel loading
    all_packages: List[Dict[str, Any]] = load_all_data_sync(
        client=api_client,
        endpoint="/v2/packages/active",
        license_number=license["licenseNumber"],
    )

    # Use the interactive collection handler to let user choose what to do
    if all_packages:
        interactive_collection_handler(
            data=all_packages,
            collection_name="packages",
            license_number=license["licenseNumber"]
        )
    else:
        print_warning("No packages found for this license.")


if __name__ == "__main__":
    main()
