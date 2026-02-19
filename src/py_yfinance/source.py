from datetime import date, datetime, timedelta
from typing import Any, Iterator, List, Optional

import pycountry
import yfinance as yf
from pydantic_market_data.interfaces import DataSource
from pydantic_market_data.models import OHLCV, History, HistoryPeriod, SecurityCriteria, Symbol
from yfinance import Search


class YFinanceDataSource(DataSource):
    """
    DataSource implementation using yfinance.
    """
    def __init__(self):
        pass

    def _map_country(self, country_name: Optional[str]) -> Optional[str]:
        """
        Map full country name (e.g., 'United States') to ISO Alpha-2 code ('US').
        """
        if not country_name:
            return None
        
        # Check if already a code
        if len(country_name) == 2 and country_name.isupper():
            return country_name

        # Look up by name
        c = pycountry.countries.get(name=country_name)
        if c:
            return c.alpha_2
        
        # Fuzzy / common mappings if pycountry fails
        # yfinance sometimes uses "United States" which pycountry handles, 
        # but maybe "USA"?
        try:
            c = pycountry.countries.lookup(country_name)
            if c:
                return c.alpha_2
        except LookupError:
            pass


    def search(self, query: str) -> List[Symbol]:
        """
        Search for securities using yfinance.Search.
        """
        s = Search(query)
        results = []
        for q in s.quotes:
            symbol_ticker = q.get("symbol")
            if not symbol_ticker:
                continue

            name = q.get("shortname", q.get("longname"))
            if not isinstance(name, str):
                name = "Unknown"

            exchange = q.get("exchange")
            if not isinstance(exchange, str):
                exchange = None

            # Map quote to Symbol
            sym = Symbol(
                ticker=str(symbol_ticker),
                name=name,
                exchange=exchange,
                country=self._map_country(q.get("country")),
                currency=None,  # Search results might not have currency, resolved later
            )
            results.append(sym)
        return results

    def lookup(self, query: str) -> List[Symbol]:
        """
        Lookup securities using yfinance.Lookup.
        """
        lookup = yf.Lookup(query)
        df = lookup.get_all()

        if df.empty:
            return []

        results = []
        for symbol, row in df.iterrows():
            name = row.get("shortName")
            if not isinstance(name, str):
                name = "Unknown"

            exchange = row.get("exchange")
            if not isinstance(exchange, str):
                exchange = None

            sym = Symbol(
                ticker=str(symbol),
                name=name,
                exchange=exchange,
                country=None,  # Lookup data does not provide country
                currency=None,
            )
            results.append(sym)
        return results

    def resolve(self, criteria: SecurityCriteria) -> Optional[Symbol]:
        """
        Resolve a security based on provided criteria.
        Prioritizes ISIN > Symbol.
        Validates against target_price if provided.
        Ensures the candidate ticker has valid historical data.
        """
        candidates = self._generate_candidates(criteria)

        seen = set()

        for candidate in candidates:
            # candidate is now a dict with metadata
            ticker = candidate.get("symbol")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)

            data = self._validate_candidate_data(
                ticker, criteria.target_date, criteria.target_price
            )
            if not data:
                continue
            
            # _validate_candidate_data now returns (price, currency) only
            current_price, currency = data

            # Use metadata from Search result (candidate)
            name = candidate.get("shortname") or candidate.get("longname") or "Unknown"
            exchange = candidate.get("exchange")
            country = self._map_country(candidate.get("country"))
            asset_class = candidate.get("quoteType") or candidate.get("typeDisp")
            
            return Symbol(
                ticker=ticker,
                name=name,
                exchange=exchange,
                country=country,
                currency=currency,
                asset_class=asset_class,
            )

    def _generate_candidates(self, criteria: SecurityCriteria) -> Iterator[dict]:
        """
        Yields dictionaries containing metadata from yfinance.Search.
        """
        if criteria.symbol:
            s = Search(criteria.symbol, max_results=100, news_count=0, lists_count=0)
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol and symbol.startswith(criteria.symbol):
                    yield q

        if criteria.isin:
            s = Search(criteria.isin, max_results=100, news_count=0, lists_count=0)
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol and not symbol.startswith(criteria.isin):
                    yield q

    def _validate_candidate_data(
        self, 
        ticker: str, 
        target_date: Optional[date] = None, 
        target_price: Optional[float] = None
    ) -> Optional[tuple]:
        """
        Validates ticker data and returns (price, currency).
        """
        t = yf.Ticker(ticker)

        if target_date:
            hist = t.history(start=target_date.strftime("%Y-%m-%d"),
                             end=(target_date + timedelta(days=1)).strftime("%Y-%m-%d"))
        else:
            hist = t.history(period="5d")

        if hist.empty:
            return None

        row = hist.iloc[0]

        if target_price:
            if not float(row["Low"]) <= target_price <= float(row["High"]):
                return None

        current_price = float(row["Close"])
                
        if current_price == 0.0:
            return None

        currency = t._price_history._history_metadata.get('currency')

        return current_price, currency


    def history(self, ticker: str, period: HistoryPeriod = HistoryPeriod.MO1) -> History:
        """
        Fetch historical data for a ticker.
        """
        period_str = period.value
        t = yf.Ticker(ticker)
        df = t.history(period=period_str)
        
        candles = []
        for index, row in df.iterrows():
            candles.append(
                OHLCV(
                    date=index,
                    open=row.get("Open"),
                    high=row.get("High"),
                    low=row.get("Low"),
                    close=row.get("Close"),
                    volume=row.get("Volume"),
                )
            )

        return History(
            symbol=Symbol(ticker=ticker, name=ticker),  # Simplified
            candles=candles,
        )

    def get_price(self, ticker: str) -> float:
        """
        Get the current price using a single efficient history call.
        """
        t = yf.Ticker(ticker)
        
        # Using a small date window with explicit interval="1d" is the most robust 
        # way to get the last price in a single request across yfinance versions.
        from datetime import date, timedelta
        end_date = date.today() + timedelta(days=1)
        start_date = end_date - timedelta(days=5) # 5 days to cover weekends
        
        # Explicit interval="1d" and auto_adjust=False ensures a single, fast request
        hist = t.history(
            start=start_date.isoformat(), 
            end=end_date.isoformat(), 
            interval="1d", 
            auto_adjust=False, 
            actions=False
        )
        if not hist.empty:
             return float(hist.iloc[-1]["Close"])
             
        # Fallback to fast_info only if history failed
        try:
            if t.fast_info and t.fast_info.last_price is not None:
                 return float(t.fast_info.last_price)
        except Exception:
            pass
        
        return 0.0

    def validate(self, ticker: str, target_date: Any, target_price: float) -> bool:
        """
        Validates if the ticker traded near the target price on the target date.
        """
        if isinstance(target_date, str):
            try:
                dt = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                return False
        elif isinstance(target_date, datetime):
            dt = target_date.date()
        else:
            dt = target_date
            
        result = self._validate_candidate_data(ticker, dt, target_price)
        return result is not None
