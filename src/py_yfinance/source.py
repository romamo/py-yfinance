import datetime
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pycountry
import yfinance as yf  # type: ignore
from pydantic_extra_types.country import CountryAlpha2
from pydantic_market_data.interfaces import DataSource
from pydantic_market_data.models import (
    OHLCV,
    AssetClass,
    History,
    HistoryPeriod,
    Price,
    PriceOnDate,
    PriceVerificationError,
    QuoteCurrency,
    Security,
    SecurityQuery,
    Symbol,
)
from yfinance import Search  # type: ignore

_YAHOO_QUOTE_TYPE_TO_ASSET_CLASS: dict[str, AssetClass] = {
    "EQUITY": AssetClass.EQUITY,
    "ETF": AssetClass.EQUITY,
    "MUTUALFUND": AssetClass.EQUITY,
    "CRYPTOCURRENCY": AssetClass.CRYPTO,
    "CURRENCY": AssetClass.FX,
    "INDEX": AssetClass.INDEX,
    "FUTURE": AssetClass.DERIVATIVE,
    "OPTION": AssetClass.DERIVATIVE,
    "BOND": AssetClass.FIXED_INCOME,
    "COMMODITY": AssetClass.COMMODITY,
}

_ASSET_CLASS_TO_YAHOO_QUOTE_TYPES: dict[AssetClass, frozenset[str]] = {
    asset_class: frozenset(
        quote_type
        for quote_type, mapped in _YAHOO_QUOTE_TYPE_TO_ASSET_CLASS.items()
        if mapped is asset_class
    )
    for asset_class in AssetClass
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidatedCandidate:
    """
    Value object containing strictly typed market data.
    """

    price: Price
    currency: QuoteCurrency | None


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

            try:
                data = self._validate_price_points(Symbol(symbol_str), criteria.price_on or [])
                if not data:
                    continue

                if criteria.currency:
                    # Both sides are QuoteCurrency, so Yahoo's "GBp" and a query's "GBp"
                    # or "GBX" compare equal as pence, and never equal to "GBP"
                    target_currency = QuoteCurrency(str(criteria.currency))
                    if data.currency != target_currency:
                        logger.debug(
                            f"Skipping {symbol_str}: Currency {data.currency} "
                            f"does not match expected {target_currency}"
                        )
                        continue
            except PriceVerificationError as e:
                logger.debug(f"Candidate {symbol_str} failed verification: {e}")
                continue

            # Use metadata from Search result (candidate)
            name = candidate.get("shortname") or candidate.get("longname") or "Unknown"
            country = self._map_country(candidate.get("country"))
            raw_quote_type = (candidate.get("quoteType") or candidate.get("typeDisp") or "").upper()
            asset_class = _YAHOO_QUOTE_TYPE_TO_ASSET_CLASS.get(raw_quote_type)
            security_type = raw_quote_type.capitalize() if raw_quote_type else None

            logger.debug(f"Resolved {symbol_str} as {name} ({raw_quote_type})")
            return SearchResult(
                symbol=Symbol(symbol_str),
                name=name,
                exchange=exchange,
                country=country,
                currency=data.currency,
                asset_class=asset_class,
                security_type=security_type,
                isin=criteria.isin,
                price=data.price,
            )
        return None

    def _validate_price_points(
        self, symbol: Symbol, price_points: list[PriceOnDate]
    ) -> ValidatedCandidate | None:
        """
        Validates a candidate against every price point; the candidate must match all of them.
        Returns the data for the most recent point, or the latest data when there are none.
        """
        if not price_points:
            return self._validate_candidate_data(symbol)

        data: ValidatedCandidate | None = None
        for point in sorted(price_points, key=lambda p: p.date):
            price = point.price if isinstance(point.price, Price) else Price(point.price)
            data = self._validate_candidate_data(symbol, point.date, price)
            if data is None:
                return None
        return data

    def _generate_candidates(self, criteria: SecurityQuery) -> Iterator[dict[str, Any]]:
        """
        Yields dictionaries containing metadata from yfinance.Search.
        ISIN candidates are yielded first, then symbol candidates, matching the
        documented resolution priority (ISIN > Symbol).
        """
        # Map request asset_class to Yahoo quoteTypes. An asset class Yahoo has no
        # quoteType for matches nothing, to prevent incorrect matches.
        target_quote_types: frozenset[str] | None = None
        if criteria.asset_class:
            target_quote_types = _ASSET_CLASS_TO_YAHOO_QUOTE_TYPES[criteria.asset_class]
            if not target_quote_types:
                return

        def matches_asset_class(q: dict[str, Any]) -> bool:
            if target_quote_types is None:
                return True
            q_type = q.get("quoteType", "").upper()
            if q_type in target_quote_types:
                return True
            logger.debug(
                f"Skipping {q['symbol']}: Yahoo type {q_type} not in {sorted(target_quote_types)}"
            )
            return False

        if criteria.isin:
            isin_str = str(criteria.isin)
            s = Search(isin_str, max_results=100, news_count=0, lists_count=0)
            for q in s.quotes:
                if q.get("symbol") and matches_asset_class(q):
                    yield q

        if criteria.symbol:
            symbol_str = str(criteria.symbol)
            s = Search(symbol_str, max_results=100, news_count=0, lists_count=0)
            for q in s.quotes:
                symbol = q.get("symbol")
                if symbol and matches_asset_class(q) and symbol.startswith(symbol_str):
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
        currency = QuoteCurrency(raw_currency) if raw_currency else None
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
