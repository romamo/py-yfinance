# Project Overview: py-yfinance

A structured Python interface for retrieving and validating market data using `yfinance`. This project implements the `DataSource` protocol from `pydantic-market-data`, providing a type-safe and validated way to interact with Yahoo Finance data.

## Key Technologies
- **Python 3.10+**
- **[uv](https://github.com/astral-sh/uv)**: Dependency management and project isolation.
- **[yfinance](https://github.com/ranaroussi/yfinance)**: The underlying data source.
- **[pydantic-market-data](https://github.com/romamo/pydantic-market-data)**: Provides the interfaces and models for market data.
- **[pydantic-settings](https://github.com/pydantic/pydantic-settings)**: Powers the CLI.
- **Pytest**: For testing.
- **Ruff & Mypy**: For linting and type safety.

## Architecture
- **`src/py_yfinance/source.py`**: Contains `YFinanceDataSource`, the primary implementation of the `DataSource` protocol. It handles searching, security resolution (ISIN/Symbol), price validation, and historical data fetching.
- **`src/py_yfinance/cli.py`**: Implements a robust CLI for interacting with the library.
- **`src/py_yfinance/logging_utils.py`**: Configures logging, supporting `-v` (INFO) and `-vv` (DEBUG) flags.

## Building and Running

### Development Setup
```bash
# Install dependencies
uv sync
```

### Running the CLI
```bash
# Lookup by Symbol
uv run yfinance lookup --ticker AAPL

# Lookup by ISIN with Price Validation
uv run yfinance lookup --isin NL0010273215 --date 2025-12-15 --price 923.4

# Fetch History
uv run yfinance history AAPL --period 1mo
```

### Testing and Quality
```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src

# Linting
uv run ruff check .

# Type Checking
uv run mypy src
```

## Development Conventions

### Coding Style
- **Type Hints**: Mandatory. The project uses `mypy` for strict type checking.
- **Linting**: Follow `ruff` defaults (configured in `pyproject.toml`).
- **Pydantic Models**: All market data entities are passed around as Pydantic models (from `pydantic-market-data`).

### Testing Practices
- **Protocols**: When adding new features, ensure they align with the `DataSource` protocol.
- **Validation**: Price and date validation are core features; any changes to resolution logic must be thoroughly tested against historical edge cases.
- **Integration**: `tests/test_integration.py` contains tests that hit the live Yahoo Finance API. Be mindful of rate limits.

### Adding New Features
- If adding a new data retrieval method, first check if it should be part of the `DataSource` protocol in `pydantic-market-data`.
- Update the CLI in `src/py_yfinance/cli.py` to expose new functionality.
- Add an example in `examples/` if it's a significant library feature.
