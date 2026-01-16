import sys
import xml.etree.ElementTree as ET

from pydantic_market_data.models import SecurityCriteria

from py_yfinance.source import YFinanceDataSource


def test_portseido_xml(xml_path):
    print(f"Parsing {xml_path}...")
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Failed to parse XML: {e}")
        return

    source = YFinanceDataSource()

    trades = root.findall(".//Trade")
    print(f"Found {len(trades)} trades.")

    unique_resolutions = {}

    for trade in trades:
        symbol = trade.get("symbol")
        isin = trade.get("isin")
        exchange = trade.get("exchange")
        description = trade.get("description")
        listing_exchange = trade.get("listingExchange")

        # Create a key for unique check
        key = (symbol, isin, exchange)
        if key in unique_resolutions:
            continue

        print(
            f"Resolving: Symbol={symbol}, ISIN={isin}, "
            f"Exch={exchange}, ListingExch={listing_exchange}"
        )

        # Prepare preferred exchanges
        preferred = []
        if exchange:
            preferred.append(exchange)
        if listing_exchange and listing_exchange != exchange:
            preferred.append(listing_exchange)

        criteria = SecurityCriteria(
            isin=isin, symbol=symbol, description=description, preferred_exchanges=preferred
        )

        resolved = source.resolve(criteria)
        unique_resolutions[key] = resolved

        if resolved:
            print(f"  -> FOUND: {resolved.ticker} ({resolved.name})")
        else:
            print("  -> NOT FOUND")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_portseido.py <path_to_xml>")
        sys.exit(1)

    test_portseido_xml(sys.argv[1])
