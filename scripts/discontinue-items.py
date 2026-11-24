#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["t3api-utils>=2.0"]
# ///
"""Discontinue every item named in input.csv.

Every row is validated with a dry run first. Nothing is sent to Metrc unless
all rows pass (or you choose to send only the valid ones).
"""

from pathlib import Path

import t3api_utils as t3

INPUT = Path(__file__).with_name("input.csv")


def main() -> None:
    with t3.connect() as client:
        license = client.license or client.pick_license()
        items = client.collect("METRC_ACTIVE_ITEMS", license=license, mask=["id", "name"])
        matches = t3.filter_rows(items, INPUT, columns=["name"], on_unmatched="error")
        result = client.bulk(
            "/v2/items/discontinue",
            rows=[{"id": item["id"]} for item in matches],
            license=license,
            submit=True,
            log_to="discontinue-results.csv",
        )
        print(result.summary())


if __name__ == "__main__":
    main()
