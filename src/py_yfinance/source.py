from typing import List, Optional, Union, Iterator, Any
from datetime import date, datetime

import pycountry
import yfinance as yf
from yfinance import Search
from pydantic_market_data.interfaces import DataSource
from pydantic_market_data.models import OHLCV, History, HistoryPeriod, SecurityCriteria, Symbol


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

        try:
            # Look up by name
            c = pycountry.countries.get(name=country_name)
            if c:
                return c.alpha_2
            
            # Fuzzy / common mappings if pycountry fails
            # yfinance sometimes uses "United States" which pycountry handles, 
            # but maybe "USA"?
            c = pycountry.countries.lookup(country_name)
            if c:
                return c.alpha_2
        except LookupError:
            pass
        
        return None


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
        l = yf.Lookup(query)
        df = l.get_all()

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
        best_match = None
        min_diff = float("inf")

        for candidate_ticker in candidates:
            if candidate_ticker in seen:
                continue
            seen.add(candidate_ticker)

            data = self._validate_candidate_data(candidate_ticker, criteria.target_date, criteria.target_price)
            if not data:
                continue
            
            current_price, currency, info = data

            return Symbol(
                ticker=info.get("symbol", candidate_ticker),
                name=info.get("longName", info.get("shortName", "Unknown")),
                exchange=info.get("exchange"),
                country=self._map_country(info.get("country")),
                currency=currency,
            )

    def _generate_candidates(self, criteria: SecurityCriteria) -> Iterator[str]:
        if criteria.symbol:
            s = Search(criteria.symbol, max_results=100, news_count=0, lists_count=0)
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol and symbol.startswith(criteria.symbol):
                    yield symbol
            # suffixes = self._get_suffixes(criteria.preferred_exchanges)
            # for suffix in suffixes:
            #     yield f"{criteria.symbol}{suffix}"

        if criteria.isin:
            s = Search(criteria.isin)
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol and not symbol.startswith(criteria.isin):
                    yield symbol

    def _validate_candidate_data(self, ticker: str, target_date: Optional[date], target_price: Optional[float] = None) -> Optional[tuple]:
        try:
            t = yf.Ticker(ticker)
        except ValueError:
            return None
        current_price = 0.0
        currency = "USD"
        info = {}

        # 1. Date Validation (if requested)
        if target_date:
            from datetime import datetime, timedelta
            if isinstance(target_date, str):
                dt_start = datetime.fromisoformat(target_date)
            else:
                dt_start = datetime.combine(target_date, datetime.min.time())
            
            # Fetch a small window around the target date to ensure we get data
            # Market might be closed on exact date, so we take the next available
            dt_end = dt_start + timedelta(days=1)
            start_str = dt_start.strftime("%Y-%m-%d")
            end_str = dt_end.strftime("%Y-%m-%d")

            hist_date = t.history(start=start_str, end=end_str)
            if not hist_date.empty:
                # We found data. 
                # If target_price is provided, we can do a "Range Match" on the first available record
                # This is more robust than just checking Close because intraday volatility might have hit the price
                
                row = hist_date.iloc[0]
                current_price = float(row["Close"])
                
                # Try validation against High/Low if price provided
                if target_price and target_price > 0:
                     low = float(row["Low"])
                     high = float(row["High"])
                     
                     # Check currency mismatch potential (GBp vs GBP)
                     # If target is 150 and price is 1.5, or target 1.5 and price 150.
                     # We handle basic scaling validation in resolve(), but here we can return the *best* matching price from the range 
                     # to avoid immediate rejection if Close didn't match but Low/High did.
                     
                     # Simple logic: If target price is within Low-High, using that as current_price 
                     # effectively says "Yes, this price was reached on this day".
                     if not low <= target_price <= high:
                         return None
                         
                currency = t.info.get('currency', 'USD')
                info = t.info 
            else:
                return None
        
        else:
            # 2. Basic Validation (5d history) - Only if no target date
            hist = t.history(period="5d")
            if not hist.empty:
                current_price = float(hist.iloc[-1]["Close"])
                currency = t.history_metadata.get("currency", t.info.get("currency", "USD"))
                info = t.info
            else:
                pass

        if current_price == 0.0:
            return None
            
        return current_price, currency, info

    def _get_suffixes(self, exchanges: Optional[List[str]]) -> List[str]:
        if not exchanges:
            return []

        mapping = {
            "IBIS": ".DE",
            "IBIS2": ".DE",
            "GER": ".DE",
            "XETRA": ".DE",
            "AEB": ".AS",
            "AMS": ".AS",
            "LSE": ".L",
            "LSEETF": ".L",
            "EUDARK": ".L",
            "PA": ".PA",
            "PAR": ".PA",
            "MIL": ".MI",
            "EBS": ".SW",  # SIX Swiss Exchange often maps to .SW? Or maybe it's EBS FX?
            # Actually EBS in IBKR often means Swiss for stocks/ETFs.
            # But for crypto/some ETFs it could be different.
            # Stuttgart? usually .SG or .ST? Yahoo uses .SG sometimes or just .DE (Xetra/Regional).
            "SWB": ".SG",
            "SWB2": ".SG",
            # Gettex often shares pricing with Xetra or uses .DE or .MU (Munich)?
            "GETTEX": ".DE",
            "GETTEX2": ".DE",
            "NASDAQ": "",
            "NYSE": "",
            "AMEX": "",
        }

        suffixes = []
        for ex in exchanges:
            # clean exchange string logic if needed
            ex_upper = ex.upper()
            if ex_upper in mapping:
                s = mapping[ex_upper]
                if s not in suffixes:
                    suffixes.append(s)

        # Add generic checks if needed? No, stick to explicit for now.
        return suffixes

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
        Get the current price (fast_info).
        """
        try:
            t = yf.Ticker(ticker)
            if t.fast_info and t.fast_info.last_price is not None:
                return float(t.fast_info.last_price)

            # Fallback to history
            hist = t.history(period="1d")
            if not hist.empty:
                return float(hist.iloc[-1]["Close"])
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
