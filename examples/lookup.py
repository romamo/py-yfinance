import argparse
import sys

from pydantic_market_data.models import SecurityCriteria

# Ensure src is in path or package is installed
# If installed as editable, we can import directly
from py_yfinance.source import YFinanceDataSource


def main():
    parser = argparse.ArgumentParser(description="Lookup ticker symbol using yfinance.")
    parser.add_argument("--isin", type=str, help="ISIN of the security")
    parser.add_argument("--symbol", type=str, help="Symbol")
    parser.add_argument("--desc", type=str, help="Description")
    parser.add_argument("--exchange", type=str, help="Exchange")

    # Validation params
    parser.add_argument("--price", type=float, help="Validation price")
    parser.add_argument("--date", type=str, help="Validation date")

    args = parser.parse_args()

    source = YFinanceDataSource()

    criteria = SecurityCriteria(
        isin=args.isin,
        symbol=args.symbol,
        description=args.desc,
        target_price=args.price,
        target_date=args.date,
        # exchange=args.exchange  TODO: since 0.1.10
    )

    symbol = source.resolve(criteria)

    if symbol:
        print(symbol.ticker)
        sys.exit(0)
    else:
        sys.exit(1)  # Not found


if __name__ == "__main__":
    main()
