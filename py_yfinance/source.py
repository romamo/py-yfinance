from typing import List, Optional

import pycountry
import yfinance as yf
from pydantic_market_data.interfaces import DataSource
from pydantic_market_data.models import OHLCV, History, HistoryPeriod, SecurityCriteria, Symbol


class YFinanceDataSource(DataSource):
    """
    DataSource implementation using yfinance.
    """

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
        # ... (rest of search implementation) ...
        # Simplified for brevity in this replace block, merging context
        try:
            t = yf.Ticker(query)
            info = t.info
            if "symbol" in info:
                return [
                    Symbol(
                        ticker=info["symbol"],
                        name=info.get("longName", info.get("shortName", "Unknown")),
                        exchange=info.get("exchange"),
                        country=self._map_country(info.get("country")),
                        currency=info.get("currency"),
                    )
                ]
        except Exception:
            pass
        return []

        return []

    def resolve(self, criteria: SecurityCriteria) -> Optional[Symbol]:
        """
        Resolve a security based on provided criteria.
        Prioritizes ISIN > Symbol.
        Validates against target_price if provided.
        """
        candidates = []

        # 1. Search by ISIN (if available)
        # yfinance Ticker(ISIN) often works directly for some ISINs or requires mapping
        if criteria.isin:
            # Try ISIN directly (sometimes supported)
            candidates.append(criteria.isin)
            # Try searching (if we had a search API)
            found = self.search(criteria.isin)
            for f in found:
                candidates.append(f.ticker)

        # 2. Search by Symbol
        if criteria.symbol:
            candidates.append(criteria.symbol)

            # Try appending suffix based on preferred exchanges
            suffixes = self._get_suffixes(criteria.preferred_exchanges)
            for suffix in suffixes:
                candidates.append(f"{criteria.symbol}{suffix}")

        seen = set()
        best_match = None
        min_diff = float("inf")

        for candidate_ticker in candidates:
            if candidate_ticker in seen:
                continue
            seen.add(candidate_ticker)

            try:
                t = yf.Ticker(candidate_ticker)

                # Validation Data
                # Use fast_info for current price check (approximate validation)
                # Or history if target_date is provided

                current_price = 0.0
                currency = "USD"

                # Validation Logic
                if criteria.target_date:
                    # Date-based validation
                    # Try to fetch history around target_date
                    # Note: yfinance expects YYYY-MM-DD. 
                    # We assume input is compatible or we might need parsing.
                    # We'll fetch a small window to ensure we catch the trading day.
                    try:
                        # Assuming target_date is YYYY-MM-DD
                        # simple approach: start=target_date, period=3d 
                        # to cover weekends/holidays if exact date is off?
                        # Or just start=target_date
                        # simple approach: start=target_date, period=3d...

                        # We need to handle potential parsing. For now assuming isoformat string.
                        # If date is '2023-12-01', we can pass it directly to start.
                        # end is exclusive, so we might need next day?
                        # To be safe, let's just use period around it or start/end.
                        # But history(start=...) works best.
                        # Parse target_date to calculate end date
                        from datetime import datetime, timedelta

                        try:
                            # flexible parsing? For now assume ISO YYYY-MM-DD
                            dt_start = datetime.fromisoformat(criteria.target_date)
                        except ValueError:
                            # try parsing YYYYMMDD just in case
                            dt_start = datetime.strptime(criteria.target_date, "%Y%m%d")

                        dt_end = dt_start + timedelta(days=5)

                        start_str = dt_start.strftime("%Y-%m-%d")
                        end_str = dt_end.strftime("%Y-%m-%d")

                        hist = t.history(start=start_str, end=end_str)

                        if not hist.empty:
                            # Verify availability
                            # For simple validation, let's take the first available row.
                            current_price = float(hist.iloc[0]["Close"])
                            # metadata might be on t.history_metadata or we assume currency
                            currency = t.history_metadata.get(
                                "currency", t.info.get("currency", "USD")
                            )
                    except Exception as e:
                        print(f"DEBUG: Date history fetch failed: {e}")
                        pass

                # Fallback or No Date provided: Check Current Price (Fast Info)
                if current_price == 0.0:
                    # Check Fast Info
                    if t.fast_info and t.fast_info.last_price is not None:
                        current_price = float(t.fast_info.last_price)
                        currency = t.fast_info.currency
                    else:
                        # Fallback to recent history
                        hist = t.history(period="5d")
                        if not hist.empty:
                            current_price = float(hist.iloc[-1]["Close"])
                            currency = t.history_metadata.get("currency", "USD")

                if current_price == 0.0:
                    continue

                # PRICE VALIDATION
                if criteria.target_price and criteria.target_price > 0:
                    # We need to be careful with currency.
                    # If target_price is in USD, and ticker is in GBP (GBp?), 
                    # we might have mismatch.
                    # Simple heuristic: if diff > 50%, skip.

                    # GBp vs GBP Handling:
                    # Yahoo often reports UK stocks in Pence (GBp).
                    # If price is ~100x target, it's likely pence.

                    price_to_check = current_price
                    if currency == "GBp" and criteria.target_price < (current_price / 50):
                        price_to_check = current_price / 100.0

                    diff = abs(price_to_check - criteria.target_price) / criteria.target_price

                    if diff < 0.01:  # 1% tolerance (strict)
                        # Keep best match
                        if diff < min_diff:
                            min_diff = diff
                            info = t.info
                            best_match = Symbol(
                                ticker=info.get("symbol", candidate_ticker),
                                name=info.get("longName", info.get("shortName", "Unknown")),
                                exchange=info.get("exchange"),
                                country=self._map_country(info.get("country")),
                                currency=currency,
                            )
                else:
                    # No target price, just accept first valid
                    info = t.info
                    return Symbol(
                        ticker=info.get("symbol", candidate_ticker),
                        name=info.get("longName", info.get("shortName", "Unknown")),
                        exchange=info.get("exchange"),
                        country=self._map_country(info.get("country")),
                        currency=currency,
                    )

            except Exception:
                continue

        return best_match

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
