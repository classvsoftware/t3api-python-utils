import json

import duckdb


def insert_dicts_autotype(table_name, data, con):
    if not data:
        raise ValueError("Data list is empty")

    # Flatten dicts: serialize nested dicts to JSON strings
    processed = [
        {
            k: json.dumps(v, default=str) if isinstance(v, dict) else v
            for k, v in row.items()
        }
        for row in data
    ]

    # Get column names and types from first row
    columns = processed[0].keys()
    placeholders = ', '.join(['?'] * len(columns))
    colnames = ', '.join(columns)

    # Create table with inferred types using first row
    con.execute(f"""
        CREATE TABLE {table_name} AS
        SELECT * FROM (VALUES ({placeholders})) AS t({colnames})
    """, tuple(processed[0].values()))

    # Insert the rest
    for row in processed[1:]:
        con.execute(f"INSERT INTO {table_name} VALUES ({placeholders})", tuple(row.values()))
        