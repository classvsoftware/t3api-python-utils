"""Constants for file output utilities."""

PRIORITY_FIELDS = [
    "hostname",
    "licenseNumber",
    "retrievedAt",
    "dataModel",
    "index",
    "id",
    "label",
    "name",
]
"""Fields that appear first (in this order) when generating CSV column headers.

These are the most commonly referenced Metrc fields and are placed at the
beginning of CSV output for readability.
"""
