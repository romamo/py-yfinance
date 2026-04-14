from pydantic_market_data.models import SecurityCriteria

from py_yfinance.source import YFinanceDataSource


def main():
    source = YFinanceDataSource()

    scenarios = [
        {"symbol": "AAPL", "desc": "Simple US Stock"},
        {"symbol": "4GLD", "exchanges": ["IBIS"], "desc": "German ETF (needs .DE suffix)"},
        {"symbol": "ASML", "exchanges": ["AEB"], "desc": "Dutch Stock"},
        {"symbol": "INVALID123", "desc": "Non-existent symbol"},
    ]

    print(f"{'Description':<30} | {'Input':<15} | {'Resolved Symbol':<15} | {'Name'}")
    print("-" * 90)

    for s in scenarios:
        criteria = SecurityCriteria(symbol=s["symbol"])
        security = source.resolve(criteria)

        input_str = s["symbol"]
        if s.get("exchanges"):
            input_str += f" ({s['exchanges'][0]})"

        symbol_str = security.symbol.root if security else "N/A"
        name = security.name if security else "-"

        print(f"{s['desc']:<30} | {input_str:<15} | {symbol_str:<15} | {name}")


if __name__ == "__main__":
    main()
