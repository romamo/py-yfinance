from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any, Iterator

import pycountry
import yfinance as yf  # type: ignore
from pydantic_extra_types.country import CountryAlpha2
from pydantic_market_data.interfaces import DataSource
from pydantic_market_data.models import (
    OHLCV,
    Currency,
    History,
    HistoryPeriod,
    Price,
    PriceVerificationError,
    Security,
    SecurityQuery,
    Symbol,
)
from yfinance import Search  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidatedCandidate:
    """
    Value object containing strictly typed market data.
    """

    price: Price
    currency: Currency | None


class SearchResult(Security):
    """
    Extended Security with optional price information.
    """

    price: Price | None = None


class YFinanceDataSource(DataSource):
    """
    DataSource implementation using yfinance.
    """

    def _map_country(self, country_name: str | None) -> CountryAlpha2 | None:
        """
        Map full country name (e.g., 'United States') to ISO Alpha-2 code ('US').
        """
        if not country_name:
            return None

        # Check if already a code
        if len(country_name) == 2 and country_name.isupper():
            return CountryAlpha2(country_name)

        # Look up by name
        c = pycountry.countries.get(name=country_name)
        if c:
            return CountryAlpha2(c.alpha_2)

        # Fuzzy / common mappings if pycountry fails
        try:
            c = pycountry.countries.lookup(country_name)
            if c:
                return CountryAlpha2(c.alpha_2)
        except (LookupError, AttributeError):
            logger.debug(f"Could not map country name: {country_name}")
        return None

    def search(self, query: str) -> list[Security]:
        """
        Search for securities using yfinance.Search.
        """
        s = Search(query)
        results = []
        for q in s.quotes:
            symbol_str = q.get("symbol")
            if not symbol_str:
                continue

            name = q.get("shortname", q.get("longname"))
            if not isinstance(name, str):
                name = "Unknown"

            exchange = q.get("exchange")
            if not isinstance(exchange, str):
                exchange = None

            # Map quote to Security
            sec = Security(
                symbol=Symbol(symbol_str),
                name=name,
                exchange=exchange,
                country=self._map_country(q.get("country")),
                currency=None,  # Search results might not have currency, resolved later
            )
            results.append(sec)
        return results

    def lookup(self, query: str) -> list[Security]:
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

            sec = Security(
                symbol=Symbol(str(symbol)),
                name=name,
                exchange=exchange,
                country=None,  # Lookup data does not provide country
                currency=None,
            )
            results.append(sec)
        return results

    def resolve(self, criteria: SecurityQuery) -> SearchResult | None:
        """
        Resolve a security based on provided criteria.
        Prioritizes ISIN > Symbol.
        Validates against price_on if provided.
        Ensures the candidate symbol has valid historical data.
        """
        candidates = self._generate_candidates(criteria)

        logger.debug(f"Resolving {criteria.isin or criteria.symbol}...")
        seen = set()
        for candidate in candidates:
            # candidate is now a dict with metadata
            symbol_str = candidate.get("symbol")
            if not symbol_str or symbol_str in seen:
                continue
            seen.add(symbol_str)

            exchange = candidate.get("exchange")
            if criteria.exchange and exchange and criteria.exchange.lower() not in exchange.lower():
                logger.debug(
                    f"Skipping {symbol_str}: Exchange {exchange} does not match "
                    f"expected {criteria.exchange}"
                )
                continue

            target_date = criteria.price_on.date if criteria.price_on else None

            target_price_vo: Price | None = None
            if criteria.price_on is not None:
                raw = criteria.price_on.price
                target_price_vo = raw if isinstance(raw, Price) else Price(raw)

            try:
                data = self._validate_candidate_data(
                    Symbol(symbol_str), target_date, target_price_vo
                )
                if not data:
                    continue

                if criteria.currency:
                    target_currency = (
                        criteria.currency
                        if isinstance(criteria.currency, Currency)
                        else Currency(str(criteria.currency))
                    )
                    actual_currency = (
                        data.currency
                        if isinstance(data.currency, Currency)
                        else Currency(str(data.currency))
                        if data.currency
                        else None
                    )

                    if actual_currency != target_currency:
                        logger.debug(
                            f"Skipping {symbol_str}: Currency {actual_currency} "
                            f"({type(actual_currency)}) does not match expected "
                            f"{target_currency} ({type(target_currency)})"
                        )
                        continue
            except PriceVerificationError as e:
                logger.debug(f"Candidate {symbol_str} failed verification: {e}")
                continue

            # Use metadata from Search result (candidate)
            name = candidate.get("shortname") or candidate.get("longname") or "Unknown"
            country = self._map_country(candidate.get("country"))
            asset_class = candidate.get("quoteType") or candidate.get("typeDisp")

            logger.debug(f"Resolved {symbol_str} as {name} ({asset_class})")
            return SearchResult(
                symbol=Symbol(symbol_str),
                name=name,
                exchange=exchange,
                country=country,
                currency=data.currency,
                asset_class=asset_class,
                isin=criteria.isin,
                price=data.price,
            )
        return None

    def _generate_candidates(self, criteria: SecurityQuery) -> Iterator[dict[str, Any]]:
        """
        Yields dictionaries containing metadata from yfinance.Search.
        ISIN candidates are yielded first, then symbol candidates, matching the
        documented resolution priority (ISIN > Symbol).
        """
        if criteria.isin:
            isin_str = str(criteria.isin)
            s = Search(isin_str, max_results=100, news_count=0, lists_count=0)
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol:
                    yield q

        if criteria.symbol:
            symbol_str = str(criteria.symbol)
            s = Search(symbol_str, max_results=100, news_count=0, lists_count=0)

            # Map request asset_class to Yahoo quoteType
            target_quote_type = None
            if criteria.asset_class:
                ac = str(criteria.asset_class).upper()
                if "CRYPTO" in ac:
                    target_quote_type = "CRYPTOCURRENCY"
                elif "STOCK" in ac or "EQUITY" in ac:
                    target_quote_type = "EQUITY"
                elif "ETF" in ac:
                    target_quote_type = "ETF"
                elif "INDEX" in ac:
                    target_quote_type = "INDEX"
                elif "CURR" in ac:
                    target_quote_type = "CURRENCY"
                else:
                    # If an asset class was requested but is unrecognizable,
                    # we must fail the search to prevent incorrect matches.
                    return

            for q in s.quotes:
                symbol = q.get("symbol")
                if not symbol:
                    continue

                # Apply asset_class filtering if requested
                if target_quote_type:
                    q_type = q.get("quoteType", "").upper()
                    if q_type != target_quote_type:
                        logger.debug(
                            f"Skipping {symbol}: Yahoo type {q_type} != {target_quote_type}"
                        )
                        continue

                if symbol.startswith(symbol_str):
                    yield q

    def _validate_candidate_data(
        self,
        symbol: Symbol.Input,
        target_date: datetime.date | None = None,
        target_price: Price.Input | None = None,
        price_tolerance: float | None = None,
    ) -> ValidatedCandidate | None:
        """
        Validates symbol data and returns strictly-typed candidate data.
        """
        symbol_vo = Symbol(symbol) if not isinstance(symbol, Symbol) else symbol
        symbol_str = symbol_vo.root
        t = yf.Ticker(symbol_str)

        if target_date:
            hist = t.history(
                start=(target_date - datetime.timedelta(days=5)).strftime("%Y-%m-%d"),
                end=(target_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            )
        else:
            hist = t.history(period="5d")

        if hist.empty:
            return None

        row = hist.iloc[-1]

        if target_price:
            target_price_vo = (
                Price(target_price) if not isinstance(target_price, Price) else target_price
            )
            price_val = round(target_price_vo.root, 2)
            low = round(float(row["Low"]), 2)
            high = round(float(row["High"]), 2)
            close = round(float(row["Close"]), 2)
            in_range = low <= price_val <= high
            if not in_range:
                if price_tolerance is not None:
                    pct_diff = abs(close - price_val) / price_val
                    if pct_diff >= price_tolerance:
                        pct_str = int(price_tolerance * 100)
                        msg = (
                            f"Price {price_val} is outside daily range"
                            f" and not within {pct_str}% of close"
                        )
                        raise PriceVerificationError(
                            msg,
                            symbol=symbol_str,
                            actual_date=target_date or datetime.date.today(),
                            expected_price=price_val,
                            actual_low=low,
                            actual_high=high,
                            actual_close=close,
                        )
                else:
                    raise PriceVerificationError(
                        f"Price {price_val} is outside daily range",
                        symbol=symbol_str,
                        actual_date=target_date or datetime.date.today(),
                        expected_price=price_val,
                        actual_low=low,
                        actual_high=high,
                        actual_close=close,
                    )

        current_price = round(float(row["Close"]), 2)

        if current_price == 0.0:
            logger.debug(f"Skipping {symbol_str}: Price is 0.0")
            return None

        # Access the private _history_metadata directly to avoid the extra HTTP
        # request that t.fast_info.currency would trigger.
        raw_currency = t._price_history._history_metadata.get("currency")
        currency = Currency(raw_currency) if raw_currency else None
        logger.debug(f"Validated data for {symbol_str}: {current_price} {raw_currency}")

        return ValidatedCandidate(
            price=Price(current_price),
            currency=currency,
        )

    def history(self, symbol: Symbol.Input, period: HistoryPeriod = HistoryPeriod.MO1) -> History:
        """
        Fetch historical data for a symbol.
        """
        symbol_vo = Symbol(symbol) if not isinstance(symbol, Symbol) else symbol
        symbol_str = symbol_vo.root
        period_str = period.value
        t = yf.Ticker(symbol_str)
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
            security=Security(symbol=symbol_vo, name=symbol_str),  # Simplified
            candles=candles,
        )

    def _fetch_close(self, t: yf.Ticker, end_date: datetime.date) -> float | None:
        """
        Fetch the most recent closing price in the 5-day window ending on end_date.
        Returns None if no data is available.
        """
        start_date = end_date - datetime.timedelta(days=5)
        hist = t.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        if not hist.empty:
            return float(hist.iloc[-1]["Close"])
        return None

    def get_price(self, symbol: Symbol.Input, date: datetime.date | None = None) -> Price:
        """
        Get the current price using a single efficient history call.
        """
        symbol_vo = Symbol(symbol) if not isinstance(symbol, Symbol) else symbol
        symbol_str = symbol_vo.root
        t = yf.Ticker(symbol_str)

        if date:
            close = self._fetch_close(t, end_date=date + datetime.timedelta(days=1))
            if close is not None:
                return Price(close)
            raise RuntimeError(f"Could not retrieve price for symbol '{symbol_str}' on {date}")

        # Current price: use today+1 as end so today's bar is included
        close = self._fetch_close(t, end_date=datetime.date.today() + datetime.timedelta(days=1))
        if close is not None:
            return Price(close)

        # Fallback to fast_info only if history failed
        if t.fast_info and t.fast_info.last_price is not None:
            return Price(float(t.fast_info.last_price))

        raise RuntimeError(f"Could not retrieve price for symbol '{symbol_str}'")

    def validate(
        self,
        symbol: Symbol.Input,
        target_date: datetime.date,
        target_price: Price.Input,
        price_tolerance: float = 0.10,
    ) -> bool:
        """
        Validates if the symbol traded near the target price on the target date.
        """
        symbol_vo = Symbol(symbol) if not isinstance(symbol, Symbol) else symbol
        price_vo = Price(target_price) if not isinstance(target_price, Price) else target_price
        result = self._validate_candidate_data(symbol_vo, target_date, price_vo, price_tolerance)
        return result is not None
