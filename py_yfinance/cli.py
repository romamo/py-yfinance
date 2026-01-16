import sys

try:
    import typer
except ImportError:
    print("Typer not installed. Please install with 'cli' extra: uv sync --extra cli")
    sys.exit(1)

from typing import List, Optional

from pydantic_market_data.models import SecurityCriteria

from py_yfinance.source import YFinanceDataSource

app = typer.Typer(help="py-yfinance CLI")
source = YFinanceDataSource()


@app.command()
def lookup(
    symbol: Optional[str] = typer.Option(None, help="Symbol to search for"),
    isin: Optional[str] = typer.Option(None, help="ISIN to search for"),
    exchange: Optional[List[str]] = typer.Option(None, help="Preferred exchanges"),
    price: Optional[float] = typer.Option(None, help="Target price for validation"),
    date: Optional[str] = typer.Option(
        None, help="Target date for validation (YYYY-MM-DD or similar)"
    ),
):
    """
    Lookup a security by Symbol or ISIN.
    """
    criteria = SecurityCriteria(
        isin=isin, symbol=symbol, preferred_exchanges=exchange, target_price=price, target_date=date
    )

    result = source.resolve(criteria)

    if result:
        print(f"Ticker: {result.ticker}")
        print(f"Name: {result.name}")
        print(f"Exchange: {result.exchange}")
        print(f"Currency: {result.currency}")
    else:
        print("Not found.")
        raise typer.Exit(code=1)


@app.command()
def history(
    ticker: str = typer.Argument(..., help="Ticker symbol"),
    period: str = typer.Option("1mo", help="Period (e.g. 1d, 5d, 1mo, 1y)"),
):
    """
    Get historical data for a ticker.
    """
    try:
        hist = source.history(ticker, period=period)
        print(f"Symbol: {hist.symbol.ticker}")
        print(f"Candles: {len(hist.candles)}")

        if hist.candles:
            last = hist.candles[-1]
            print(f"Last Candle ({last.date}): Close=${last.close}")

    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
