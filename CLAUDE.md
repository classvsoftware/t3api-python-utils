# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- **`http/`** - HTTP utilities (new module)
- **`main/`** - Main utility functions that orchestrate other modules

### Core Interfaces
- `HasData[T]` - Protocol for objects with a `data` attribute containing lists
- `SerializableObject` - Protocol for objects with `index`, `license_number`, and `to_dict()` method
- `T3Credentials` - Authentication credentials interface

### Key Dependencies
- **T3 API Integration**: Uses `t3api` client for Track & Trace Tools platform
- **Data Processing**: DuckDB + PyArrow for high-performance data operations
- **CLI**: Typer for command-line interfaces with Rich for output formatting
- **Type Safety**: Full mypy strict typing enforced

### Data Flow Pattern
1. **Authentication** (`auth/`) - Create authenticated API clients
2. **Collection** (`collection/`) - Parallel data fetching from T3 API
3. **Processing** (`db/`) - Flatten nested data and create relational tables
4. **Output** (`file/`) - Export to CSV/JSON formats

### Configuration Notes
- MyPy is configured with strict settings including `disallow_untyped_defs`
- Python 3.8+ compatibility required
- Uses `uv.lock` for dependency resolution