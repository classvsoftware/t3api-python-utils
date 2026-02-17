# t3api-utils

Python utilities for the T3 (Track and Trace Tools) API.

Provides authentication, data collection, processing, and export tools for working with Metrc cannabis regulatory data through the T3 API.

## Installation

```bash
uv pip install t3api-utils
```

## Quick Start

```python
from t3api_utils.main.utils import get_authenticated_client_or_error
from t3api_utils.api.operations import get_collection

# Authenticate (interactive picker for credentials, JWT, or API key)
client = get_authenticated_client_or_error()

# Fetch a paginated collection
response = get_collection(client, "/v2/packages", license_number="LIC-0001")
```

## Package Overview

| Module | Description |
|---|---|
| [`api`](reference/api-client.md) | httpx-based API client with async support and paginated collection fetching |
| [`auth`](reference/auth.md) | Authentication utilities for credentials, JWT, and API key flows |
| [`http`](reference/http.md) | Low-level httpx client construction with retry policies and rate limiting |
| [`db`](reference/db.md) | DuckDB-backed data flattening, table creation, and schema export |
| [`file`](reference/file.md) | CSV/JSON serialization and file output utilities |
| [`collection`](reference/collection.md) | Parallel data loading and extraction helpers |
| [`openapi`](reference/openapi.md) | OpenAPI spec fetching and interactive endpoint selection |
| [`cli`](reference/cli.md) | CLI configuration management and interactive credential prompting |
| [`style`](reference/style.md) | Rich console theming and styled message helpers |
| [`inspector`](reference/inspector.md) | Textual TUI for interactive collection browsing |

## Data Flow

1. **Authentication** (`auth`) - Create authenticated httpx-based API clients
2. **Collection** (`api`) - Parallel data fetching with rate limiting
3. **Processing** (`db`) - Flatten nested data and create relational tables
4. **Output** (`file`) - Export to CSV/JSON formats
