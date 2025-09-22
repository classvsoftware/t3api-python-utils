# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Strategy

- The data returned from Metrc collection API endpoints may slightly change over time. Extra fields may be added. Don't write python classes that assume an exact data shape, they should fall back gracefully.

## Development Setup

This project uses `uv` for Python package management:

```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e .[dev]
```

### Essential Commands

```bash
# Testing
pytest                    # Run all tests
pytest tests/specific/    # Run specific test directory

# Type checking
mypy t3api_utils tests    # Type check source and tests

# Type generation (if needed)
python bin/generate_types.py  # Update TypedDict definitions from OpenAPI spec
```

## Architecture

### Package Structure
The `t3api_utils` package is organized into focused modules:

- **`auth/`** - Authentication utilities for T3 API credentials and client creation
- **`api/`** - httpx-based T3 API client with async support and enhanced features
- **`db/`** - Database utilities using DuckDB for data processing and table creation
- **`file/`** - File I/O operations including CSV/JSON serialization
- **`http/`** - HTTP utilities using httpx with retry policies and rate limiting
- **`main/`** - Main utility functions that orchestrate other modules

### Core Interfaces
- `HasData[T]` - Protocol for objects with a `data` attribute containing lists
- `SerializableObject` - Protocol for objects with `index`, `license_number`, and `to_dict()` method
- `T3Credentials` - Authentication credentials interface
- `PaginatedResponse[T]` - Protocol for paginated API responses

### Data Flow
1. **Authentication** (`auth/`) - Create authenticated httpx-based API clients
2. **Collection** (`api/`) - Enhanced parallel data fetching with rate limiting
3. **Processing** (`db/`) - Flatten nested data and create relational tables
4. **Output** (`file/`) - Export to CSV/JSON formats

### Key Dependencies
- **httpx >= 0.25.0** - HTTP client with async support
- **DuckDB + PyArrow** - High-performance data operations
- **Typer + Rich** - CLI interfaces with purple-themed output
- **MyPy** - Strict typing enforced with `disallow_untyped_defs`

## Authentication

### Interactive Picker (Recommended)
```python
from t3api_utils.main.utils import get_authenticated_client_or_error

# Shows interactive picker with authentication options
client = get_authenticated_client_or_error()
```

**Picker Features:**
- Rich table display with consistent purple styling
- Clear descriptions for each authentication method
- Input validation and keyboard interrupt handling
- Automatic routing to appropriate auth flow

### Direct Authentication Methods

**Credentials Authentication:**
```python
client = create_credentials_authenticated_client_or_error(
    hostname="...",
    username="...",
    password="..."
)
```
- Interactive prompts for hostname, username, password
- Automatic credential saving to `.t3.env` file
- Environment variable support for automation

**JWT Token Authentication:**
```python
# Basic JWT authentication
client = get_jwt_authenticated_client_or_error(jwt_token="your_jwt_token_here")

# JWT with validation (recommended)
client = get_jwt_authenticated_client_or_error_with_validation(jwt_token="your_jwt_token_here")
```
- Automatic token validation via `/v2/auth/whoami` endpoint
- Clear error messages for expired/invalid tokens
- Automatic client cleanup on validation failure

### Auto-Generated TypedDict Interfaces

The `interfaces/` directory contains auto-generated TypedDict definitions from the OpenAPI specification:

```python
# Import specific types
from interfaces import MetrcLicense, MetrcPackage, SearchResponse

# Use in type annotations
def process_licenses(licenses: List[MetrcLicense]) -> None:
    for license in licenses:
        print(license["licenseName"])  # Full type safety with dict access
```

**Benefits:**
- Always up-to-date from live OpenAPI spec
- Complete API schema coverage
- Full MyPy support with TypedDict
- Flexible handling of optional fields with `NotRequired[]`

## Testing

Unit test coverage should be 100%

## CLI Standards

### Color Palette

**Primary Purple Theme:**
- `primary` - `#8B5CF6` (Violet-500) - Headers, titles, primary actions
- `accent` - `#A855F7` (Purple-500) - Highlights, emphasis, interactive elements
- `muted` - `#C4B5FD` (Violet-300) - Secondary text, subdued information
- `bright` - `#DDD6FE` (Violet-200) - Backgrounds, subtle highlights

**Status Colors:**
- `success` - `#10B981` (Emerald-500) - Success messages, completed actions
- `error` - `#EF4444` (Red-500) - Error messages, failures
- `warning` - `#F59E0B` (Amber-500) - Warnings, cautions
- `info` - `#6366F1` (Indigo-500) - Information, help text

### Style Conventions

**Message Types:**
```python
# Success, Error, Warning, Info, Progress
console.print("[bold green]✓[/bold green] Operation completed successfully")
console.print("[bold red]✗[/bold red] Operation failed: {error_message}")
console.print("[bold yellow]⚠[/bold yellow] Warning: {warning_message}")
console.print("[bold blue]ℹ[/bold blue] {info_message}")
console.print("[bold magenta]⋯[/bold magenta] {status_message}")
```

**Headers and Structure:**
```python
# Main headers, section headers, sub-headers
console.print("[bold magenta]═══ {title} ═══[/bold magenta]")
console.print("[bold bright_magenta]── {section_name} ──[/bold bright_magenta]")
console.print("[magenta]{sub_header}:[/magenta]")
```

**Interactive Elements:**
```python
# Tables, prompts, file paths
table = Table(border_style="magenta", header_style="bold magenta")
user_input = typer.prompt("[magenta]Enter your choice[/magenta]")
console.print(f"[cyan]{file_path}[/cyan]")
```

### Implementation Guidelines

**Centralized Styling:**
- Use `t3api_utils.style` module for all styling constants
- Import styled console: `from t3api_utils.style import console, style`
- Never use plain `print()` - always use Rich console

**Consistency Rules:**
- All success messages use green with checkmark: `[bold green]✓[/bold green]`
- All error messages use red with X mark: `[bold red]✗[/bold red]`
- All progress/status use purple with dots: `[bold magenta]⋯[/bold magenta]`
- All headers use magenta with decorative borders

**Accessibility:**
- Always include symbols (✓, ✗, ⚠, ℹ, ⋯) alongside colors
- Use `bold` for important messages to improve readability
- Maintain good contrast ratios

### CLI Picker Standards

All selection interfaces should use consistent Rich Table formatting:

**Standard Implementation:**
```python
from rich.table import Table
from t3api_utils.style import console

def pick_something(items: List[SomeType]) -> SomeType:
    """Standard picker implementation."""
    table = Table(title="Available Items", border_style="magenta", header_style="bold magenta")
    table.add_column("#", style="magenta", justify="right")
    table.add_column("Name", style="bright_white")
    table.add_column("Details", style="cyan")  # Optional third column

    for i, item in enumerate(items, 1):
        table.add_row(str(i), item.name, item.details)

    console.print(table)
    choice = typer.prompt("Select item (number)", type=int)
    # ... validation and return logic
```

**Requirements:**
- Rich Table with magenta border styling
- Numbered selection column with `style="magenta", justify="right"`
- Primary content column with `style="bright_white"`
- Optional details column with `style="cyan"`
- Always validate user input range
- Always handle keyboard interruption gracefully

**Examples in Codebase:**
- `pick_license()` in `t3api_utils/main/utils.py`
- `pick_file()` in `t3api_utils/main/utils.py`
- `pick_collection()` in `t3api_utils/openapi/collection_picker.py`
- `interactive_collection_handler()` in `t3api_utils/main/utils.py`