from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
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
    SecurityCriteria,
    Symbol,
    Ticker,
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


class SearchResult(Symbol):
    """
    Extended Symbol with optional price information.
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

    def search(self, query: str) -> list[Symbol]:
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

    def lookup(self, query: str) -> list[Symbol]:
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

    def resolve(self, criteria: SecurityCriteria) -> SearchResult | None:
        """
        Resolve a security based on provided criteria.
        Prioritizes ISIN > Symbol.
        Validates against target_price if provided.
        Ensures the candidate ticker has valid historical data.
        """
        candidates = self._generate_candidates(criteria)

        logger.debug(f"Resolving {criteria.isin or criteria.symbol}...")
        seen = set()
        for candidate in candidates:
            # candidate is now a dict with metadata
            ticker = candidate.get("symbol")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)

            exchange = candidate.get("exchange")
            if criteria.exchange and exchange and criteria.exchange.lower() not in exchange.lower():
                logger.debug(
                    f"Skipping {ticker}: Exchange {exchange} does not match "
                    f"expected {criteria.exchange}"
                )
                continue

            target_date = criteria.target_date

            target_price_vo: Price | None = None
            if criteria.target_price is not None:
                raw = criteria.target_price
                target_price_vo = raw if isinstance(raw, Price) else Price(raw)

            try:
                data = self._validate_candidate_data(Ticker(ticker), target_date, target_price_vo)
                if not data:
                    continue
            except PriceVerificationError as e:
                logger.debug(f"Candidate {ticker} failed verification: {e}")
                continue

            # Use metadata from Search result (candidate)
            name = candidate.get("shortname") or candidate.get("longname") or "Unknown"
            country = self._map_country(candidate.get("country"))
            asset_class = candidate.get("quoteType") or candidate.get("typeDisp")

            logger.debug(f"Resolved {ticker} as {name} ({asset_class})")
            return SearchResult(
                ticker=ticker,
                name=name,
                exchange=exchange,
                country=country,
                currency=data.currency,
                asset_class=asset_class,
                isin=criteria.isin,
                price=data.price,
            )
        return None

    def _generate_candidates(self, criteria: SecurityCriteria) -> Iterator[dict[str, Any]]:
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
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol and symbol.startswith(symbol_str):
                    yield q

    def _validate_candidate_data(
        self,
        ticker: Ticker.Input,
        target_date: date | None = None,
        target_price: Price.Input | None = None,
    ) -> ValidatedCandidate | None:
        """
        Validates ticker data and returns strictly-typed candidate data.
        """
        ticker_vo = Ticker(ticker) if not isinstance(ticker, Ticker) else ticker
        ticker_str = ticker_vo.root
        t = yf.Ticker(ticker_str)

        if target_date:
            hist = t.history(
                start=(target_date - timedelta(days=5)).strftime("%Y-%m-%d"),
                end=(target_date + timedelta(days=1)).strftime("%Y-%m-%d"),
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
            if not low <= price_val <= high:
                raise PriceVerificationError(
                    f"Price {price_val} is outside daily range",
                    ticker=ticker_str,
                    actual_date=target_date or date.today(),
                    expected_price=price_val,
                    actual_low=low,
                    actual_high=high,
                    actual_close=close,
                )

        current_price = round(float(row["Close"]), 2)

        if current_price == 0.0:
            logger.debug(f"Skipping {ticker_str}: Price is 0.0")
            return None

        # Access the private _history_metadata directly to avoid the extra HTTP
        # request that t.fast_info.currency would trigger.
        raw_currency = t._price_history._history_metadata.get("currency")
        currency = Currency(raw_currency) if raw_currency else None
        logger.debug(f"Validated data for {ticker_str}: {current_price} {raw_currency}")

        return ValidatedCandidate(
            price=Price(current_price),
            currency=currency,
        )

    def history(self, ticker: Ticker.Input, period: HistoryPeriod = HistoryPeriod.MO1) -> History:
        """
        Fetch historical data for a ticker.
        """
        ticker_vo = Ticker(ticker) if not isinstance(ticker, Ticker) else ticker
        ticker_str = ticker_vo.root
        period_str = period.value
        t = yf.Ticker(ticker_str)
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
            symbol=Symbol(ticker=ticker_vo, name=ticker_str),  # Simplified
            candles=candles,
        )

    def _fetch_close(self, t: yf.Ticker, end_date: date) -> float | None:
        """
        Fetch the most recent closing price in the 5-day window ending on end_date.
        Returns None if no data is available.
        """
        start_date = end_date - timedelta(days=5)
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

    def get_price(self, ticker: Ticker.Input, as_of: date | None = None) -> Price:
        """
        Get the current price using a single efficient history call.
        """
        ticker_vo = Ticker(ticker) if not isinstance(ticker, Ticker) else ticker
        ticker_str = ticker_vo.root
        t = yf.Ticker(ticker_str)

        if as_of:
            close = self._fetch_close(t, end_date=as_of + timedelta(days=1))
            if close is not None:
                return Price(close)
            raise RuntimeError(f"Could not retrieve price for ticker '{ticker_str}' on {as_of}")

        # Current price: use today+1 as end so today's bar is included
        close = self._fetch_close(t, end_date=date.today() + timedelta(days=1))
        if close is not None:
            return Price(close)

        # Fallback to fast_info only if history failed
        if t.fast_info and t.fast_info.last_price is not None:
            return Price(float(t.fast_info.last_price))

        raise RuntimeError(f"Could not retrieve price for ticker '{ticker_str}'")

    def validate(self, ticker: Ticker.Input, target_date: date, target_price: Price.Input) -> bool:
        """
        Validates if the ticker traded near the target price on the target date.
        """
        ticker_vo = Ticker(ticker) if not isinstance(ticker, Ticker) else ticker
        price_vo = Price(target_price) if not isinstance(target_price, Price) else target_price
        # Pass already-coerced VOs; _validate_candidate_data accepts Ticker/Price directly.
        result = self._validate_candidate_data(ticker_vo, target_date, price_vo)
        return result is not None
