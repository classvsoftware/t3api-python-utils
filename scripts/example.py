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

import duckdb

from t3api_utils.api.parallel import load_all_data_sync
from t3api_utils.db.utils import export_duckdb_schema
from t3api_utils.file.utils import open_file, save_dicts_to_csv
from t3api_utils.main.utils import (get_authenticated_client_or_error, load_db,
                                    pick_license)


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

    # Load data into DuckDB
    con = duckdb.connect()
    load_db(con=con, data=all_packages)

    # Export and print database schema
    print(export_duckdb_schema(con=con))

    # Save packages to CSV using the direct file utility
    if all_packages:
        csv_path = save_dicts_to_csv(
            dicts=all_packages,
            model_name="packages",
            license_number=license["licenseNumber"],
            output_dir="output",
            strip_empty_columns=True
        )
        print(f"Saved {len(all_packages)} packages to {csv_path}")

        # Optionally open the file
        open_file(path=csv_path)
    else:
        print("No packages found for this license.")


if __name__ == "__main__":
    main()
