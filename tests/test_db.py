"""Tests for database utility functions."""

import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import duckdb
import pytest

from t3api_utils.db.utils import (
    _extract_nested_list,
    _is_list_of_nested_dicts,
    create_duckdb_connection,
    create_table_from_data,
    export_duckdb_constraints,
    export_duckdb_schema,
    flatten_and_extract,
)


class TestCreateDuckDBConnection:
    """Tests for create_duckdb_connection function."""

    def test_create_memory_connection(self):
        """Test creating an in-memory DuckDB connection."""
        con = create_duckdb_connection()
        assert isinstance(con, duckdb.DuckDBPyConnection)
        # Test that we can execute a simple query
        result = con.execute("SELECT 1 as test").fetchone()
        assert result == (1,)
        con.close()

    def test_create_file_connection(self):
        """Test creating a file-based DuckDB connection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            con = create_duckdb_connection(database=str(db_path))
            assert isinstance(con, duckdb.DuckDBPyConnection)

            # Create a table and verify it persists
            con.execute("CREATE TABLE test (id INT)")
            con.execute("INSERT INTO test VALUES (42)")
            con.close()

            # Reopen and verify data persists
            con2 = create_duckdb_connection(database=str(db_path))
            result = con2.execute("SELECT * FROM test").fetchone()
            assert result == (42,)
            con2.close()

    def test_create_readonly_connection(self):
        """Test creating a read-only DuckDB connection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "readonly_test.db"
            # First create a database with some data
            con = create_duckdb_connection(database=str(db_path))
            con.execute("CREATE TABLE test (id INT)")
            con.execute("INSERT INTO test VALUES (123)")
            con.close()

            # Open in read-only mode
            con_ro = create_duckdb_connection(database=str(db_path), read_only=True)

            # Should be able to read
            result = con_ro.execute("SELECT * FROM test").fetchone()
            assert result == (123,)

            # Should not be able to write
            with pytest.raises(Exception) as exc_info:
                con_ro.execute("INSERT INTO test VALUES (456)")
            # Verify it's some kind of read-only error
            assert "read" in str(exc_info.value).lower() or "only" in str(exc_info.value).lower()

            con_ro.close()

    def test_connection_kwargs_only(self):
        """Test that function requires keyword arguments."""
        with pytest.raises(TypeError):
            # Should fail with positional arguments
            create_duckdb_connection(":memory:")  # type: ignore


class TestFlattenAndExtract:
    """Tests for flatten_and_extract function."""

    def test_flatten_simple_records(self):
        """Test flattening records without nested structures."""
        data = [
            {"id": 1, "name": "Test1", "value": 100},
            {"id": 2, "name": "Test2", "value": 200}
        ]
        extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)

        result = flatten_and_extract(data=data, extracted_tables=extracted_tables)

        assert len(result) == 2
        assert result[0] == {"id": 1, "name": "Test1", "value": 100}
        assert result[1] == {"id": 2, "name": "Test2", "value": 200}
        assert len(extracted_tables) == 0

    def test_extract_nested_lists(self):
        """Test extracting nested lists with dataModel."""
        data = [
            {
                "id": 1,
                "dataModel": "Parent",
                "items": [
                    {"id": 10, "dataModel": "Child", "value": "A"},
                    {"id": 11, "dataModel": "Child", "value": "B"}
                ]
            }
        ]
        extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)

        result = flatten_and_extract(data=data, extracted_tables=extracted_tables)

        # Parent record should not have the nested list
        assert "items" not in result[0]
        assert result[0]["id"] == 1
        assert result[0]["dataModel"] == "Parent"

        # Check extracted child records
        assert "Child" in extracted_tables
        assert len(extracted_tables["Child"]) == 2
        assert extracted_tables["Child"][10]["value"] == "A"
        assert extracted_tables["Child"][10]["Parent_id"] == 1
        assert extracted_tables["Child"][11]["value"] == "B"
        assert extracted_tables["Child"][11]["Parent_id"] == 1

    def test_no_extraction_without_parent_info(self):
        """Test that nested lists are not extracted without parent id/model."""
        data = [
            {
                "name": "NoID",
                "items": [
                    {"id": 10, "dataModel": "Child", "value": "A"}
                ]
            }
        ]
        extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)

        result = flatten_and_extract(data=data, extracted_tables=extracted_tables)

        # Items should remain in the parent record
        assert result[0]["items"] == [{"id": 10, "dataModel": "Child", "value": "A"}]
        assert len(extracted_tables) == 0


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_is_list_of_nested_dicts_true(self):
        """Test _is_list_of_nested_dicts returns True for valid nested dicts."""
        value = [
            {"id": 1, "dataModel": "Test"},
            {"id": 2, "dataModel": "Test"}
        ]
        assert _is_list_of_nested_dicts(value) is True

    def test_is_list_of_nested_dicts_false_not_list(self):
        """Test _is_list_of_nested_dicts returns False for non-lists."""
        assert _is_list_of_nested_dicts("not a list") is False
        assert _is_list_of_nested_dicts({"id": 1}) is False
        assert _is_list_of_nested_dicts(123) is False

    def test_is_list_of_nested_dicts_false_empty(self):
        """Test _is_list_of_nested_dicts returns False for empty lists."""
        assert _is_list_of_nested_dicts([]) is False

    def test_is_list_of_nested_dicts_false_missing_keys(self):
        """Test _is_list_of_nested_dicts returns False when required keys missing."""
        # Missing dataModel
        assert _is_list_of_nested_dicts([{"id": 1}]) is False
        # Missing id
        assert _is_list_of_nested_dicts([{"dataModel": "Test"}]) is False
        # Mixed valid and invalid
        assert _is_list_of_nested_dicts([
            {"id": 1, "dataModel": "Test"},
            {"id": 2}  # Missing dataModel
        ]) is False

    def test_extract_nested_list(self):
        """Test _extract_nested_list function."""
        items = [
            {"id": 10, "dataModel": "Child", "name": "Item1"},
            {"id": 11, "dataModel": "Child", "name": "Item2"}
        ]
        extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)

        _extract_nested_list(
            items=items,
            parent_model="Parent",
            parent_id=1,
            extracted_tables=extracted_tables
        )

        assert "Child" in extracted_tables
        assert len(extracted_tables["Child"]) == 2
        assert extracted_tables["Child"][10]["name"] == "Item1"
        assert extracted_tables["Child"][10]["Parent_id"] == 1
        assert extracted_tables["Child"][11]["name"] == "Item2"
        assert extracted_tables["Child"][11]["Parent_id"] == 1


class TestCreateTableFromData:
    """Tests for create_table_from_data function."""

    def test_create_table_from_list(self):
        """Test creating table from a list of dicts."""
        con = create_duckdb_connection()
        data = [
            {"id": 1, "name": "Alice", "age": 30},
            {"id": 2, "name": "Bob", "age": 25}
        ]

        create_table_from_data(con=con, data_dict=data, name="users")

        result = con.execute("SELECT * FROM users ORDER BY id").fetchall()
        assert len(result) == 2
        assert result[0] == (1, "Alice", 30)
        assert result[1] == (2, "Bob", 25)
        con.close()

    def test_create_table_from_dict(self):
        """Test creating table from a deduplicated dict."""
        con = create_duckdb_connection()
        data = {
            1: {"id": 1, "name": "Alice", "age": 30},
            2: {"id": 2, "name": "Bob", "age": 25}
        }

        create_table_from_data(con=con, data_dict=data, name="users")

        result = con.execute("SELECT * FROM users ORDER BY id").fetchall()
        assert len(result) == 2
        con.close()

    def test_create_table_infer_name(self):
        """Test creating table with inferred name from dataModel."""
        con = create_duckdb_connection()
        data = [
            {"id": 1, "dataModel": "Product", "name": "Widget"},
            {"id": 2, "dataModel": "Product", "name": "Gadget"}
        ]

        # Name should be inferred from dataModel
        create_table_from_data(con=con, data_dict=data)

        result = con.execute('SELECT * FROM "Product" ORDER BY id').fetchall()
        assert len(result) == 2
        # Check the name column (should be the third column after id and dataModel)
        row = result[0]
        assert "Widget" in row or row[2] == "Widget"
        con.close()

    def test_create_table_replaces_existing(self):
        """Test that creating a table replaces existing table."""
        con = create_duckdb_connection()

        # Create initial table
        data1 = [{"id": 1, "value": "old"}]
        create_table_from_data(con=con, data_dict=data1, name="test")

        # Replace with new data
        data2 = [{"id": 2, "value": "new"}]
        create_table_from_data(con=con, data_dict=data2, name="test")

        result = con.execute('SELECT * FROM "test"').fetchall()
        assert len(result) == 1
        assert result[0] == (2, "new")
        con.close()

    def test_create_table_empty_data_raises(self):
        """Test that empty data raises ValueError."""
        con = create_duckdb_connection()

        with pytest.raises(ValueError, match="No data to create table"):
            create_table_from_data(con=con, data_dict=[], name="test")

        with pytest.raises(ValueError, match="No data to create table"):
            create_table_from_data(con=con, data_dict={}, name="test")

        con.close()

    def test_create_table_missing_name_and_model_raises(self):
        """Test that missing name and dataModel raises ValueError."""
        con = create_duckdb_connection()
        data = [{"id": 1, "value": "test"}]  # No dataModel field

        with pytest.raises(ValueError, match="Missing dataModel key"):
            create_table_from_data(con=con, data_dict=data)

        con.close()


class TestExportDuckDBSchema:
    """Tests for export_duckdb_schema function."""

    def test_export_schema_single_table(self):
        """Test exporting schema for a single table."""
        con = create_duckdb_connection()
        con.execute("CREATE TABLE users (id INTEGER, name VARCHAR, age INTEGER)")

        schema = export_duckdb_schema(con=con)

        assert "Table: users" in schema
        assert "- id: INTEGER" in schema
        assert "- name: VARCHAR" in schema
        assert "- age: INTEGER" in schema
        con.close()

    def test_export_schema_multiple_tables(self):
        """Test exporting schema for multiple tables."""
        con = create_duckdb_connection()
        con.execute("CREATE TABLE users (id INTEGER, name VARCHAR)")
        con.execute("CREATE TABLE posts (id INTEGER, user_id INTEGER, title VARCHAR)")

        schema = export_duckdb_schema(con=con)

        assert "Table: users" in schema
        assert "Table: posts" in schema
        assert "- user_id: INTEGER" in schema
        con.close()

    def test_export_schema_with_foreign_key_inference(self):
        """Test that foreign key relationships are inferred."""
        con = create_duckdb_connection()
        con.execute("CREATE TABLE users (id INTEGER, name VARCHAR)")
        con.execute("CREATE TABLE posts (id INTEGER, users_id INTEGER, title VARCHAR)")

        schema = export_duckdb_schema(con=con)

        assert "Inferred Relationships:" in schema
        assert "posts.users_id → users.id" in schema
        con.close()

    def test_export_schema_empty_database(self):
        """Test exporting schema from empty database."""
        con = create_duckdb_connection()

        schema = export_duckdb_schema(con=con)

        # Should return empty or minimal output
        assert "Table:" not in schema
        assert "Inferred Relationships:" not in schema
        con.close()


class TestExportDuckDBConstraints:
    """Tests for export_duckdb_constraints function."""

    def test_export_constraints_no_constraints(self):
        """Test exporting constraints when there are none."""
        con = create_duckdb_connection()
        con.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")

        constraints = export_duckdb_constraints(con=con)

        # DuckDB doesn't create constraints by default
        assert isinstance(constraints, list)
        con.close()

    def test_export_constraints_with_primary_key(self):
        """Test exporting constraints with primary key."""
        con = create_duckdb_connection()
        con.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name VARCHAR)")

        constraints = export_duckdb_constraints(con=con)

        assert isinstance(constraints, list)
        # Note: Exact constraint format depends on DuckDB version
        con.close()

    def test_export_constraints_kwargs_only(self):
        """Test that function requires keyword arguments."""
        con = create_duckdb_connection()

        with pytest.raises(TypeError):
            # Should fail with positional arguments
            export_duckdb_constraints(con)  # type: ignore

        con.close()


class TestIntegration:
    """Integration tests for db utilities."""

    def test_full_workflow(self):
        """Test a complete workflow using multiple functions."""
        # Create sample data with nested structures
        data = [
            {
                "id": 1,
                "dataModel": "Order",
                "customer": "Alice",
                "items": [
                    {"id": 10, "dataModel": "OrderItem", "product": "Widget", "quantity": 2},
                    {"id": 11, "dataModel": "OrderItem", "product": "Gadget", "quantity": 1}
                ]
            },
            {
                "id": 2,
                "dataModel": "Order",
                "customer": "Bob",
                "items": [
                    {"id": 12, "dataModel": "OrderItem", "product": "Widget", "quantity": 3}
                ]
            }
        ]

        # Process data
        extracted_tables: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)
        flat_data = flatten_and_extract(data=data, extracted_tables=extracted_tables)

        # Create database and tables
        con = create_duckdb_connection()
        create_table_from_data(con=con, data_dict=flat_data)

        for table_name, table_data in extracted_tables.items():
            create_table_from_data(con=con, data_dict=table_data)

        # Verify Order table
        orders = con.execute('SELECT * FROM "Order" ORDER BY id').fetchall()
        assert len(orders) == 2
        assert orders[0][2] == "Alice"  # customer column
        assert orders[1][2] == "Bob"

        # Verify OrderItem table with foreign keys
        items = con.execute('SELECT * FROM "OrderItem" ORDER BY id').fetchall()
        assert len(items) == 3
        # Check that Order_id foreign keys are set
        assert items[0][4] == 1  # First two items belong to order 1
        assert items[1][4] == 1
        assert items[2][4] == 2  # Third item belongs to order 2

        # Export and verify schema
        schema = export_duckdb_schema(con=con)
        assert "Table: Order" in schema
        assert "Table: OrderItem" in schema
        assert "OrderItem.Order_id → Order.id" in schema

        con.close()