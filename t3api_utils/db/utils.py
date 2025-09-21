from typing import Any, Dict, List, Set, Tuple, Union

import duckdb
import pyarrow as pa  # type: ignore[import-untyped]

from t3api_utils.db.consts import ID_KEY, ID_SUFFIX, MODEL_KEY, SCHEMA_NAME


def create_duckdb_connection(
    *,
    database: str = ":memory:",
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """
    Creates and returns a DuckDB connection with configurable settings.

    This provides a centralized way to create DuckDB connections that can be
    extended with additional configuration options as needed.

    Args:
        database: Database path or ":memory:" for in-memory database (default: ":memory:")
        read_only: Whether to open the database in read-only mode (default: False)

    Returns:
        DuckDB connection object

    Example:
        >>> con = create_duckdb_connection()  # In-memory database
        >>> con = create_duckdb_connection(database="mydata.db")  # File-based database
        >>> con = create_duckdb_connection(database="mydata.db", read_only=True)  # Read-only
    """
    return duckdb.connect(database=database, read_only=read_only)


def flatten_and_extract(
    *,
    data: List[Dict[str, Any]],
    extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Flattens nested records and extracts referenced dicts and lists of dicts into separate tables.

    Args:
        data: A list of top-level dictionaries containing nested dicts and/or lists.
        extracted_tables: A dictionary to collect deduplicated records by table name.

    Returns:
        A list of flattened dictionaries with references to nested entities via foreign keys.
    """
    flat_data: List[Dict[str, Any]] = []

    for record in data:
        flat_record = {}
        parent_id = record.get(ID_KEY)
        parent_model = record.get(MODEL_KEY)

        for key, value in record.items():
            # if _is_nested_dict(value):
            #     _extract_nested_dict(value, flat_record, extracted_tables)

            # elif
            if (
                _is_list_of_nested_dicts(value)
                and parent_id is not None
                and parent_model is not None
            ):
                _extract_nested_list(value, parent_model, parent_id, extracted_tables)

            else:
                flat_record[key] = value

        flat_data.append(flat_record)

    return flat_data


def _is_list_of_nested_dicts(value: Any) -> bool:
    """Check if a value is a list of nested dicts with IDs and data_models."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, dict) and ID_KEY in item and MODEL_KEY in item
            for item in value
        )
    )


def _extract_nested_list(
    items: List[Dict[str, Any]],
    parent_model: str,
    parent_id: Any,
    extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]],
) -> None:
    """Extract a list of nested dicts into their own tables and attach foreign key to each."""
    for item in items:
        table_name = item[MODEL_KEY]
        item_copy = dict(item)
        item_copy[f"{parent_model}{ID_SUFFIX}"] = parent_id
        extracted_tables[table_name][item[ID_KEY]] = item_copy


def export_duckdb_schema(*, con: duckdb.DuckDBPyConnection) -> str:
    """
    Exports a human-readable representation of the DuckDB schema,
    including inferred foreign key-like relationships.

    Useful for creating AI-generated queries based on the schema.

    Args:
        con: An active DuckDB connection.

    Returns:
        A string representation of the schema and inferred relationships.
    """
    tables: List[Tuple[str]] = con.execute(
        f"""
        SELECT table_name
        FROM duckdb_tables()
        WHERE schema_name = '{SCHEMA_NAME}'
        ORDER BY table_name
        """
    ).fetchall()

    schema_output: List[str] = []
    seen_columns: Set[Tuple[str, str]] = set()

    for (table_name,) in tables:
        columns: List[Tuple[str, str]] = con.execute(
            f"""
            SELECT column_name, data_type
            FROM duckdb_columns()
            WHERE schema_name = '{SCHEMA_NAME}' AND table_name = '{table_name}'
            ORDER BY column_name
            """
        ).fetchall()

        schema_output.append(f"Table: {table_name}")
        for col_name, col_type in columns:
            key = (table_name, col_name)
            if key not in seen_columns:
                seen_columns.add(key)
                schema_output.append(f"  - {col_name}: {col_type}")
        schema_output.append("")

    # Infer foreign-key-like relationships based on *_id column naming
    fk_output: Set[str] = set()

    for (table_name,) in tables:
        col_names: List[Tuple[str]] = con.execute(
            f"""
            SELECT column_name
            FROM duckdb_columns()
            WHERE schema_name = '{SCHEMA_NAME}' AND table_name = '{table_name}'
            """
        ).fetchall()

        for (col_name,) in col_names:
            if col_name.endswith(ID_SUFFIX):
                ref_table = col_name[: -len(ID_SUFFIX)]
                if any(t[0] == ref_table for t in tables):
                    relation = f"Inferred relation: {table_name}.{col_name} → {ref_table}.{ID_KEY}"
                    fk_output.add(relation)

    if fk_output:
        schema_output.append("Inferred Relationships:")
        schema_output.extend(f"  - {line}" for line in sorted(fk_output))

    return "\n".join(schema_output)


def export_duckdb_constraints(
    *, con: duckdb.DuckDBPyConnection
) -> List[Tuple[Any, ...]]:
    """
    Retrieves all schema constraints (including primary and foreign keys).

    Args:
        con: An active DuckDB connection.

    Returns:
        A list of constraint tuples.
    """
    return con.execute(
        f"""
        SELECT *
        FROM duckdb_constraints()
        ORDER BY table_name, constraint_type
        """
    ).fetchall()


def create_table_from_data(
    *,
    con: duckdb.DuckDBPyConnection,
    data_dict: Union[Dict[Any, Dict[str, Any]], List[Dict[str, Any]]],
    name: str | None = None,
) -> None:
    """
    Creates a DuckDB table from the provided data using PyArrow.
    Automatically drops and recreates the table.

    Args:
        con: An active DuckDB connection.
        data_dict: The table data, either as a list or deduplicated dict of rows.
        name: Optional name for the table. If not provided, will be inferred from data_model.

    Raises:
        ValueError: If the table name cannot be inferred or data is empty.
    """
    table_data: List[Dict[str, Any]] = (
        list(data_dict.values()) if isinstance(data_dict, dict) else data_dict
    )

    if not table_data:
        raise ValueError("No data to create table")

    if name is None:
        if MODEL_KEY not in table_data[0]:
            raise ValueError(f"Missing {MODEL_KEY} key to infer table name")
        name = table_data[0][MODEL_KEY]

    table = pa.Table.from_pylist(table_data)
    # Drop both view and table to ensure clean slate (view first, then table)
    con.execute(f'DROP VIEW IF EXISTS "{name}"')
    con.execute(f'DROP TABLE IF EXISTS "{name}"')
    con.register(name, table)
    con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM "{name}"')
