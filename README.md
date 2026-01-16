# py-yfinance

A structured Python interface for retrieving and validating market data using `yfinance`.
Implements the `DataSource` protocol from `pydantic-market-data` to provide type-safe security resolution and historical data fetching.

## Features

- **Protocol-Oriented**: Implements `DataSource` interface.
- **Security Resolution**: Resolve ISINs and Symbols to valid `yfinance` tickers.
- **Validation**:
  - **Exchanges**: Map exchanges (e.g., `IBIS`, `AEB`) to Yahoo suffixes (`.DE`, `.AS`).
  - **Price Validation**: Verify tickers against a known target price with **strict 1% tolerance**.
  - **Date Validation**: Validate prices on specific historical dates.
- **Typer CLI**: Optional command-line interface for lookup and history.

## Installation

```bash
# Basic installation
uv pip install py-yfinance

# With CLI support
uv pip install "py-yfinance[cli]"
```

## Usage

### As a Library

```python
from py_yfinance.source import YFinanceDataSource
from pydantic_market_data.models import SecurityCriteria

source = YFinanceDataSource()

# 1. Simple Lookup by Symbol
criteria = SecurityCriteria(symbol="AAPL", preferred_exchanges=["NASDAQ"])
result = source.resolve(criteria)
print(result)
# Symbol(ticker='AAPL', name='Apple Inc.', exchange='NMS', currency='USD', ...)

# 2. Strict Validation using Date & Price
# Useful for verifying ISIN mappings or ensuring data quality
criteria = SecurityCriteria(
    isin="NL0010273215",
    target_date="2025-12-15",
    target_price=923.4  # Validates against history with 1% tolerance
)
match = source.resolve(criteria)
if match:
    print(f"Verified: {match.ticker}")
else:
    print("Validation failed: Price mismatch or symbol not found")
```

### CLI Usage

Requires `[cli]` extra.

#### Lookup
Resolve a security by Symbol or ISIN.

```bash
# Basic Lookup
uv run py-yfinance lookup --symbol AAPL

# ISIN Lookup with Strict Validation
# Verifies that NL0010273215 commanded a price of ~923.4 on 2025-12-15
uv run py-yfinance lookup --isin NL0010273215 --date 2025-12-15 --price 923.4
```

#### History
Fetch historical candles.

```bash
uv run py-yfinance history AAPL --period 5d
```

## Development

This project uses `uv` for dependency management.

```bash
# Sync dependencies
uv sync --extra cli

# Run Tests
uv run pytest
```

## License

MIT
