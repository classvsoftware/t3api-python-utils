from collections import defaultdict
from typing import Any, Dict, List, Tuple, Union

import duckdb
import pyarrow as pa

from t3api_utils.db.consts import ID_KEY, ID_SUFFIX, MODEL_KEY, SCHEMA_NAME


def flatten_and_extract(
    data: List[Dict[str, Any]],
    extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    flat_data: List[Dict[str, Any]] = []

    for record in data:
        flat_record = {}
        for key, value in record.items():
            if isinstance(value, dict) and ID_KEY in value and MODEL_KEY in value:
                table_name = value[MODEL_KEY]
                extracted_tables[table_name][value[ID_KEY]] = value
                flat_record[f"{table_name}{ID_SUFFIX}"] = value[ID_KEY]
            else:
                flat_record[key] = value
        flat_data.append(flat_record)

    return flat_data


def export_duckdb_schema(con: duckdb.DuckDBPyConnection) -> str:
    tables: List[Tuple[str]] = con.execute(
        f"""
        SELECT table_name
        FROM duckdb_tables()
        WHERE schema_name = '{SCHEMA_NAME}'
        ORDER BY table_name
        """
    ).fetchall()

    schema_output: List[str] = []
    seen: set[Tuple[str, str]] = set()

    for (table_name,) in tables:
        columns: List[Tuple[str, str]] = con.execute(
            f"""
            SELECT DISTINCT column_name, data_type
            FROM duckdb_columns()
            WHERE schema_name = '{SCHEMA_NAME}' AND table_name = '{table_name}'
            ORDER BY column_name
            """
        ).fetchall()

        schema_output.append(f"Table: {table_name}")
        for col_name, col_type in columns:
            key = (table_name, col_name)
            if key not in seen:
                seen.add(key)
                schema_output.append(f"  - {col_name}: {col_type}")
        schema_output.append("")

    # Inferred FK-like relationships
    fk_output: List[str] = []
    for (table_name,) in tables:
        col_names: List[Tuple[str]] = con.execute(
            f"""
            SELECT DISTINCT column_name
            FROM duckdb_columns()
            WHERE schema_name = '{SCHEMA_NAME}' AND table_name = '{table_name}'
            """
        ).fetchall()
        for (col_name,) in col_names:
            if col_name.endswith(ID_SUFFIX):
                ref_table = col_name[: -len(ID_SUFFIX)]
                if any(t[0] == ref_table for t in tables):
                    relation = f"Inferred relation: {table_name}.{col_name} → {ref_table}.{ID_KEY}"
                    if relation not in fk_output:
                        fk_output.append(relation)

    if fk_output:
        schema_output.append("Inferred Relationships:")
        schema_output.extend(f"  - {line}" for line in fk_output)

    return "\n".join(schema_output)


def export_duckdb_constraints(con: duckdb.DuckDBPyConnection) -> List[Tuple[Any, ...]]:
    return con.execute(
        f"""
        SELECT *
        FROM duckdb_constraints()
        ORDER BY table_name, constraint_type
        """
    ).fetchall()


def create_table_from_data(
    con: duckdb.DuckDBPyConnection,
    name: str,
    data_dict: Union[Dict[Any, Dict[str, Any]], List[Dict[str, Any]]],
) -> None:
    table_data: List[Dict[str, Any]] = (
        list(data_dict.values()) if isinstance(data_dict, dict) else data_dict
    )
    table = pa.Table.from_pylist(table_data)
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.register(name, table)
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}")
