# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Strategy

- The data returned from Metrc collection API endpoints may slightly change over time. Extra fields may be added. Don't write python classes that assume an exact data shape, they should fall back gracefully. 

## Development Environment Setup

This project uses `uv` for Python package management:

```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install package in editable mode
uv pip install -e .

# Install development dependencies
uv pip install -e .[dev]
```

## Common Development Commands

### Testing
```bash
pytest                    # Run all tests
pytest tests/specific/    # Run specific test directory
```

### Type Generation
```bash
# Update TypedDict definitions from OpenAPI spec
python bin/generate_types.py

# Or use the wrapper script
./bin/update-types

# Specify custom spec URL or output directory
python bin/generate_types.py --spec-url https://api.example.com/spec --output-dir custom_interfaces
```

### Type Checking
```bash
mypy t3api_utils tests    # Type check source and tests
```

### Building and Publishing
```bash
# Build package
uv pip install build
python -m build

# Test publish to TestPyPI
uv pip install twine
twine upload --repository testpypi dist/*

# Production publish
twine upload dist/*
```

## Architecture Overview

### Package Structure
The `t3api_utils` package is organized into focused modules:

- **`auth/`** - Authentication utilities for T3 API credentials and client creation
- **`cli/`** - Command-line interface utilities and input resolution
- **`collection/`** - Data collection utilities for parallel API operations
- **`db/`** - Database utilities using DuckDB for data processing and table creation
- **`file/`** - File I/O operations including CSV/JSON serialization
- **`http/`** - HTTP utilities using httpx with retry policies and rate limiting
- **`api/`** - httpx-based T3 API client with async support and enhanced features
- **`main/`** - Main utility functions that orchestrate other modules

### Core Interfaces
- `HasData[T]` - Protocol for objects with a `data` attribute containing lists
- `SerializableObject` - Protocol for objects with `index`, `license_number`, and `to_dict()` method
- `T3Credentials` - Authentication credentials interface
- `PaginatedResponse[T]` - Protocol for paginated API responses

### Key Dependencies
- **T3 API Integration**: httpx-based implementation for modern API client functionality
  - httpx >= 0.25.0 for HTTP client functionality with async support
- **Data Processing**: DuckDB + PyArrow for high-performance data operations
- **CLI**: Typer for command-line interfaces with Rich for output formatting
- **Type Safety**: Full mypy strict typing enforced

### httpx-based API Client Features

**Usage:**
```python
# Create authenticated client
client = get_authenticated_client_or_error()
client = create_credentials_authenticated_client_or_error(hostname="...", username="...", password="...")
```

**Key Features:**
- **Async Support**: `AsyncT3APIClient` for high-performance concurrent operations
- **Rate Limiting**: Configurable requests-per-second limits to avoid API throttling
- **Enhanced Error Handling**: Better error messages and retry policies with exponential backoff
- **Batching**: Process large datasets in configurable batch sizesetc.

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

**Key Benefits:**
- **Always up-to-date**: Generated from live OpenAPI spec
- **Complete coverage**: All API schemas included
- **Type safety**: Full MyPy support with TypedDict
- **Flexible**: Handles optional fields with `NotRequired[]`

### Data Flow Pattern
1. **Authentication** (`auth/`) - Create authenticated httpx-based API clients
2. **Collection** (`collection/`, `api/`) - Enhanced parallel data fetching with rate limiting
3. **Processing** (`db/`) - Flatten nested data and create relational tables
4. **Output** (`file/`) - Export to CSV/JSON formats

### Configuration Notes
- MyPy is configured with strict settings including `disallow_untyped_defs`
- Python 3.8+ compatibility required
- Uses `uv.lock` for dependency resolution
- httpx-based HTTP client for better performance and async support

## CLI Style Guide

This project uses a **consistent purple-themed CLI interface** powered by the Rich library. All CLI output should follow these styling conventions to provide a cohesive user experience.

### Color Palette

**Primary Purple Theme:**
- `primary` - `#8B5CF6` (Violet-500) - Headers, titles, primary actions
- `accent` - `#A855F7` (Purple-500) - Highlights, emphasis, interactive elements
- `muted` - `#C4B5FD` (Violet-300) - Secondary text, subdued information
- `bright` - `#DDD6FE` (Violet-200) - Backgrounds, subtle highlights

**Status Colors (Purple-tinted):**
- `success` - `#10B981` (Emerald-500) - Success messages, completed actions
- `error` - `#EF4444` (Red-500) - Error messages, failures
- `warning` - `#F59E0B` (Amber-500) - Warnings, cautions
- `info` - `#6366F1` (Indigo-500) - Information, help text

### Style Conventions

**1. Message Types:**
```python
# Success (green with subtle purple tint)
console.print("[bold green]✓[/bold green] Operation completed successfully")

# Error (red, clear and direct)
console.print("[bold red]✗[/bold red] Operation failed: {error_message}")

# Warning (amber)
console.print("[bold yellow]⚠[/bold yellow] Warning: {warning_message}")

# Info (purple/indigo)
console.print("[bold blue]ℹ[/bold blue] {info_message}")

# Progress/Status (primary purple)
console.print("[bold magenta]⋯[/bold magenta] {status_message}")
```

**2. Headers and Titles:**
```python
# Main headers
console.print("[bold magenta]═══ {title} ═══[/bold magenta]")

# Section headers
console.print("[bold bright_magenta]── {section_name} ──[/bold bright_magenta]")

# Sub-headers
console.print("[magenta]{sub_header}:[/magenta]")
```

**3. Tables and Lists:**
```python
# Tables should use purple styling
table = Table(border_style="magenta", header_style="bold magenta")

# Lists with purple bullets
console.print("[magenta]•[/magenta] {list_item}")

# Numbered lists
console.print("[magenta]{number}.[/magenta] {list_item}")
```

**4. Interactive Elements:**
```python
# Prompts with purple styling
user_input = typer.prompt("[magenta]Enter your choice[/magenta]")

# Menu options
console.print("[magenta]{number}.[/magenta] {option_text}")

# Current state/status
console.print("[dim]Current state:[/dim] [magenta]{state_info}[/magenta]")
```

**5. File Paths and Technical Info:**
```python
# File paths in cyan for readability
console.print(f"[cyan]{file_path}[/cyan]")

# Technical details in dim
console.print(f"[dim]{technical_info}[/dim]")

# Code/data in bright white
console.print(f"[white]{code_or_data}[/white]")
```

### Implementation Guidelines

**1. Centralized Styling:**
- Use `t3api_utils.style` module for all styling constants and utilities
- Import styled console instance: `from t3api_utils.style import console, style`
- Never use plain `print()` - always use Rich console

**2. Consistency Rules:**
- All success messages use green with checkmark: `[bold green]✓[/bold green]`
- All error messages use red with X mark: `[bold red]✗[/bold red]`
- All progress/status use purple with dots: `[bold magenta]⋯[/bold magenta]`
- All headers use magenta with decorative borders

**3. Accessibility:**
- Always include symbols (✓, ✗, ⚠, ℹ, ⋯) alongside colors
- Use `bold` for important messages to improve readability
- Maintain good contrast ratios

**4. Performance:**
- Pre-define common styles to avoid string parsing overhead
- Use Rich's `Style` objects for frequently used combinations
- Cache styled strings where appropriate

### Usage Examples

**Interactive Collection Handler:**
```python
# Title
console.print("[bold magenta]═══ Collection Handler ═══[/bold magenta]")
console.print(f"[magenta]Dataset:[/magenta] {collection_name} ([bright_white]{len(data):,}[/bright_white] items)")

# Menu
console.print("\n[magenta]Options:[/magenta]")
for i, option in enumerate(options, 1):
    console.print(f"  [magenta]{i}.[/magenta] {option}")

# Status updates
console.print("[bold magenta]⋯[/bold magenta] Creating database connection...")
console.print("[bold green]✓[/bold green] Database connection established")
```

**Authentication Flow:**
```python
# Auth prompt
console.print("[bold magenta]── Authentication Required ──[/bold magenta]")
hostname = typer.prompt("[magenta]Metrc hostname[/magenta]")
username = typer.prompt("[magenta]Username[/magenta]")
password = typer.prompt("[magenta]Password[/magenta]", hide_input=True)
```

This style guide ensures a professional, cohesive purple-themed interface across all CLI interactions.