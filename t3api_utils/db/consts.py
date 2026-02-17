"""Constants used by DuckDB table creation and schema export utilities."""

SCHEMA_NAME = "main"
"""DuckDB schema name where tables are created."""

ID_SUFFIX = "_id"
"""Suffix appended to parent model names to form foreign key column names."""

ID_KEY = "id"
"""Primary key field name expected in Metrc records."""

MODEL_KEY = "dataModel"
"""Field name used to identify the data model type of a record."""
