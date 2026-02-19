import argparse
import logging
import sys

from pydantic_market_data.models import SecurityCriteria

from py_yfinance.source import YFinanceDataSource


def setup_logging(verbose: int):
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
        force=True
    )
    logging.getLogger("py_yfinance").setLevel(level)


source = YFinanceDataSource()


def lookup(args):
    """
    Lookup a security by Symbol or ISIN.
    """
    criteria = SecurityCriteria(
        isin=args.isin, 
        symbol=args.symbol, 
        target_price=args.price,
        target_date=args.date
    )

    result = source.resolve(criteria)

    if result:
        print(f"Ticker: {result.ticker}")
        print(f"Name: {result.name}")
        print(f"Exchange: {result.exchange}")
        print(f"Currency: {result.currency}")
    else:
        print("Not found.")
        sys.exit(1)


def history(args):
    """
    Get historical data for a ticker.
    """
    try:
        hist = source.history(args.ticker, period=args.period)
        print(f"Symbol: {hist.symbol.ticker}")
        print(f"Candles: {len(hist.candles)}")

        if hist.candles:
            last = hist.candles[-1]
            print(f"Last Candle ({last.date}): Close=${last.close}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    # Parent parser for shared arguments (verbose)
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (-v for INFO, -vv for DEBUG)"
    )

    parser = argparse.ArgumentParser(description="py-yfinance CLI", parents=[parent_parser])
    subparsers = parser.add_subparsers(dest="command", required=True)

    # lookup command
    p_lookup = subparsers.add_parser("lookup", parents=[parent_parser], help="Lookup a security")
    p_lookup.add_argument("--symbol", help="Symbol to search for")
    p_lookup.add_argument("--isin", help="ISIN to search for")
    p_lookup.add_argument("--exchange", nargs="+", help="Exchange")
    p_lookup.add_argument("--price", type=float, help="Target price for validation")
    p_lookup.add_argument("--date", help="Target date for validation")
    p_lookup.set_defaults(func=lookup)

    # history command
    p_history = subparsers.add_parser(
        "history", 
        parents=[parent_parser], 
        help="Get historical data"
    )
    p_history.add_argument("ticker", help="Ticker symbol")
    p_history.add_argument("--period", default="1mo", help="Period (e.g. 1d, 5d, 1mo, 1y)")
    p_history.set_defaults(func=history)

    args = parser.parse_args()

    setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
