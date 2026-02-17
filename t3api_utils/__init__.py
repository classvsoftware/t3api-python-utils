"""t3api_utils - Python utilities for the T3 (Track and Trace Tools) API.

Provides authentication, data collection, processing, and export tools
for working with Metrc cannabis regulatory data through the T3 API.

Modules:
    api: httpx-based API client with async support and paginated collection fetching.
    auth: Authentication utilities for credentials, JWT, and API key flows.
    cli: CLI configuration management and interactive credential prompting.
    collection: Parallel data loading and extraction helpers.
    db: DuckDB-backed data flattening, table creation, and schema export.
    file: CSV/JSON serialization and file output utilities.
    http: Low-level httpx client construction with retry policies and rate limiting.
    inspector: Textual TUI for interactive collection browsing.
    main: High-level orchestration tying auth, collection, and output together.
    openapi: OpenAPI spec fetching and interactive endpoint selection.
    style: Rich console theming and styled message helpers.
"""
