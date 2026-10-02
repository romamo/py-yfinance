# yfinance

A structured Python interface for retrieving and validating market data using `yfinance`.
Implements the `DataSource` protocol from `pydantic-market-data` to provide type-safe security resolution and historical data fetching.

## Features

- **Protocol-Oriented**: Implements `DataSource` interface.
- **Security Resolution**: Resolve ISINs and Symbols to valid `yfinance` tickers.
- **Validation**:
  - **Price Validation**: Verify tickers against daily high/low range.
  - **Date Validation**: Validate prices on specific historical dates.
- **CLI**: Optional command-line interface for lookup and history.

## Installation

```bash
uv pip install py-yfinance
```

## Usage

### As a Library

```python
from py_yfinance import YFinanceDataSource
from pydantic_market_data.models import PriceOnDate, SecurityQuery

source = YFinanceDataSource()

# 1. Simple lookup by symbol
result = source.resolve(SecurityQuery(symbol="AAPL"))
print(result.symbol, result.price)

# 2. Strict validation by date and price
# Useful for verifying ISIN mappings or ensuring data quality
query = SecurityQuery(
    isin="NL0010273215",
    price_on=PriceOnDate(date="2025-12-15", price=923.4),
)
match = source.resolve(query)
if match:
    print(f"Verified: {match.symbol}")
else:
    print("Validation failed: price mismatch or symbol not found")
```

Dates accept `YYYY-MM-DD`, `YYYY/MM/DD` or `YYYYMMDD`; any other string raises `ValidationError`.

### CLI Usage

#### Lookup
Resolve a security by symbol or ISIN.

```bash
# Basic lookup
uv run yfinance lookup --symbol AAPL

# ISIN lookup with strict validation
# Verifies that NL0010273215 traded near 923.4 on 2025-12-15
uv run yfinance lookup --isin NL0010273215 --date 2025-12-15 --price 923.4
```

#### History
Fetch daily candles.

```bash
uv run yfinance history --symbol AAPL --period 5d
```

#### Search

```bash
uv run yfinance search tesla
```

Output is a JSON envelope when stdout is not a terminal; pass `--format plain` for text. Run `uv run yfinance <command> --schema` for a command's input and output schema.

## Development

This project uses `uv` for dependency management.

```bash
# Sync dependencies
uv sync

# Run Tests
uv run pytest
```

## License

MIT
