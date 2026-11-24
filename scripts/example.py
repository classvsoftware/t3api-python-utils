#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["t3api-utils[tui]>=2.0"]
# ///
"""Pick a collection, load all of it, and browse the rows that match input.csv."""

from pathlib import Path

import t3api_utils as t3

INPUT = Path(__file__).with_name("input.csv")


def main() -> None:
    with t3.connect() as client:
        license = client.license or client.pick_license()
        endpoint = client.pick_endpoint(kind="collection")
        rows = client.collect(endpoint.id or endpoint.path, license=license)
        t3.inspect(rows, title=endpoint.id or endpoint.path)

        matches = t3.filter_rows(rows, INPUT, on_unmatched="warn")
        print(f"Saved {len(matches)} matching rows to {t3.to_csv(matches)}")
        t3.inspect(matches, title="matches")


if __name__ == "__main__":
    main()
