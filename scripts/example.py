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

from t3api_utils.api.interfaces import MetrcObject
from t3api_utils.api.parallel import load_all_data_sync
from t3api_utils.main.utils import (get_authenticated_client_or_error,
                                    interactive_collection_handler,
                                    match_collection_from_csv, pick_license)
from t3api_utils.openapi import pick_collection
from t3api_utils.style import print_warning


def main():
    # Get authenticated httpx-based client
    api_client = get_authenticated_client_or_error()

    # Pick a license interactively
    license = pick_license(api_client=api_client)

    selected_collection = pick_collection()

    # Load all data for the selected collection and license
    collection: List[MetrcObject] = load_all_data_sync(
        client=api_client,
        path=selected_collection["path"],
        license_number=license["licenseNumber"],
    )

    interactive_collection_handler(data=collection)

    filtered_collection = match_collection_from_csv(
        data=collection, on_no_match="error"
    )

    interactive_collection_handler(data=filtered_collection)


if __name__ == "__main__":
    main()
