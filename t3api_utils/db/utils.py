import duckdb
import pyarrow as pa


def flatten_and_extract(data, extracted_tables):
    flat_data = []
    for record in data:
        flat_record = {}
        for key, value in record.items():
            if isinstance(value, dict) and "id" in value and "data_model" in value:
                table_name = value["data_model"]
                extracted_tables[table_name][value["id"]] = value
                flat_record[f"{table_name}_id"] = value["id"]
            else:
                flat_record[key] = value
        flat_data.append(flat_record)
    return flat_data


def export_duckdb_schema(con: duckdb.DuckDBPyConnection) -> str:
    tables = con.execute(
        """
        SELECT table_name
        FROM duckdb_tables()
        WHERE schema_name = 'main'
        ORDER BY table_name
        """
    ).fetchall()

    schema_output = []
    seen = set()

    for (table_name,) in tables:
        columns = con.execute(
            f"""
            SELECT DISTINCT column_name, data_type
            FROM duckdb_columns()
            WHERE schema_name = 'main' AND table_name = '{table_name}'
            ORDER BY column_name
            """
        ).fetchall()

        schema_output.append(f"Table: {table_name}")
        for col_name, col_type in columns:
            key = (table_name, col_name)
            if key not in seen:
                seen.add(key)
                schema_output.append(f"  - {col_name}: {col_type}")
        schema_output.append("")  # newline between tables

    # Inferred FK-like relationships
    fk_output = []
    for (table_name,) in tables:
        col_names = con.execute(
            f"""
            SELECT DISTINCT column_name
            FROM duckdb_columns()
            WHERE schema_name = 'main' AND table_name = '{table_name}'
            """
        ).fetchall()
        for (col_name,) in col_names:
            if col_name.endswith("_id"):
                ref_table = col_name[:-3]
                if any(t[0] == ref_table for t in tables):
                    relation = (
                        f"Inferred relation: {table_name}.{col_name} → {ref_table}.id"
                    )
                    if relation not in fk_output:
                        fk_output.append(relation)

    if fk_output:
        schema_output.append("Inferred Relationships:")
        schema_output.extend(f"  - {line}" for line in fk_output)

    return "\n".join(schema_output)


def export_duckdb_constraints(con):
    constraints = con.execute(
        """
        SELECT *
        FROM duckdb_constraints()
        ORDER BY table_name, constraint_type
    """
    ).fetchall()

    return constraints


def create_table_from_data(con, name, data_dict):
    table_data = list(data_dict.values()) if isinstance(data_dict, dict) else data_dict
    table = pa.Table.from_pylist(table_data)
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.register(name, table)
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}")
