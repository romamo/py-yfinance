"""
Company fundamentals, analyst data, earnings dates and bulk prices from Yahoo Finance.

`YahooFundamentals` turns yfinance's loosely shaped frames and dicts into typed,
validated models. A dataset Yahoo does not have for a symbol (an ETF has no
income statement or analyst ratings) is a valid answer and comes back empty or
`None`. A failed request, or data in a shape this module does not recognise,
raises `YahooDataError`.

yfinance's `Ticker` and `download` are constructor arguments, so callers and
tests can supply their own.
"""

import datetime
import math
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import pandas as pd
import yfinance as yf  # type: ignore
from pydantic import BaseModel, ConfigDict, FiniteFloat, NonNegativeInt
from pydantic_market_data.models import HistoryPeriod, Symbol
from yfinance import exceptions as yf_exceptions  # type: ignore

# What yfinance raises when a request fails or a dataset comes back malformed
_YFINANCE_ERRORS = (yf_exceptions.YFException, KeyError, ValueError, TypeError, IndexError)

_EARNINGS_COLUMNS = ("EPS Estimate", "Reported EPS", "Surprise(%)")
_RATING_COLUMNS = ("Firm", "ToGrade", "FromGrade", "Action")
_RECOMMENDATION_COLUMNS = ("strongBuy", "buy", "hold", "sell", "strongSell")


class YahooDataError(Exception):
    """Yahoo failed to answer, or answered in a shape py-yfinance does not recognise."""

    def __init__(self, symbol: str, dataset: str, reason: str) -> None:
        super().__init__(f"{symbol}: {dataset}: {reason}")
        self.symbol = symbol
        self.dataset = dataset
        self.reason = reason


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KeyStatistics(_Model):
    """Quote summary figures; `None` where Yahoo has no meaningful value (ETFs lack most)."""

    current_price: FiniteFloat | None
    market_cap: FiniteFloat | None
    trailing_pe: FiniteFloat | None
    enterprise_to_ebitda: FiniteFloat | None
    price_to_sales_ttm: FiniteFloat | None
    price_to_book: FiniteFloat | None
    revenue_growth: FiniteFloat | None  # year over year, as a fraction
    beta: FiniteFloat | None
    total_debt: FiniteFloat | None
    total_cash: FiniteFloat | None
    ebitda: FiniteFloat | None
    free_cashflow: FiniteFloat | None
    operating_cashflow: FiniteFloat | None
    target_mean_price: FiniteFloat | None
    target_high_price: FiniteFloat | None
    target_low_price: FiniteFloat | None
    quote_type: str | None


class RecommendationCounts(_Model):
    """Analyst ratings for the latest month Yahoo reports."""

    strong_buy: NonNegativeInt
    buy: NonNegativeInt
    hold: NonNegativeInt
    sell: NonNegativeInt
    strong_sell: NonNegativeInt


class AnnualStatement(_Model):
    """One fiscal year's income statement, balance sheet and cash flow line items."""

    fiscal_year_end: datetime.date
    revenue: FiniteFloat | None
    gross_profit: FiniteFloat | None
    ebit: FiniteFloat | None
    net_income: FiniteFloat | None
    pretax_income: FiniteFloat | None
    tax_provision: FiniteFloat | None
    ebitda: FiniteFloat | None
    total_assets: FiniteFloat | None
    current_assets: FiniteFloat | None
    current_liabilities: FiniteFloat | None
    long_term_debt: FiniteFloat | None
    total_debt: FiniteFloat | None
    total_liabilities: FiniteFloat | None
    stockholders_equity: FiniteFloat | None
    retained_earnings: FiniteFloat | None
    cash: FiniteFloat | None
    shares_outstanding: FiniteFloat | None
    operating_cash_flow: FiniteFloat | None
    free_cash_flow: FiniteFloat | None
    stock_based_comp: FiniteFloat | None
    working_capital: FiniteFloat | None


class EarningsDate(_Model):
    """A scheduled or reported quarter; the reported fields are `None` until the report is out."""

    announced: datetime.datetime  # timezone-aware, as Yahoo gives it
    eps_estimate: FiniteFloat | None
    reported_eps: FiniteFloat | None
    surprise_pct: FiniteFloat | None


class RatingChange(_Model):
    """One analyst firm's rating action."""

    day: datetime.date
    firm: str
    action: str  # Yahoo's codes: up, down, main, init, reit
    from_grade: str
    to_grade: str
    price_target_action: str | None  # Raises, Lowers, Maintains, ... when Yahoo reports it


class BulkPrices(BaseModel):
    """Adjusted daily closes and volumes for many symbols, one column per symbol that has data."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    closes: pd.DataFrame
    volumes: pd.DataFrame
    missing: tuple[str, ...]  # requested symbols Yahoo returned no prices for


class _TickerLike(Protocol):
    def get_info(self) -> dict[str, Any]: ...

    @property
    def recommendations(self) -> pd.DataFrame | None: ...

    @property
    def income_stmt(self) -> pd.DataFrame | None: ...

    @property
    def balance_sheet(self) -> pd.DataFrame | None: ...

    @property
    def cashflow(self) -> pd.DataFrame | None: ...

    @property
    def upgrades_downgrades(self) -> pd.DataFrame | None: ...

    def get_earnings_dates(self, limit: int) -> pd.DataFrame | None: ...


TickerFactory = Callable[[str], _TickerLike]
Downloader = Callable[..., pd.DataFrame | None]

# (field, statement, labels tried in order): Yahoo renames some lines across companies
_STATEMENT_LINES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("revenue", "income", ("Total Revenue",)),
    ("gross_profit", "income", ("Gross Profit",)),
    ("ebit", "income", ("EBIT", "Operating Income")),
    ("net_income", "income", ("Net Income",)),
    ("pretax_income", "income", ("Pretax Income",)),
    ("tax_provision", "income", ("Tax Provision",)),
    ("ebitda", "income", ("EBITDA", "Normalized EBITDA")),
    ("total_assets", "balance", ("Total Assets",)),
    ("current_assets", "balance", ("Current Assets",)),
    ("current_liabilities", "balance", ("Current Liabilities",)),
    ("long_term_debt", "balance", ("Long Term Debt",)),
    ("total_debt", "balance", ("Total Debt",)),
    ("total_liabilities", "balance", ("Total Liabilities Net Minority Interest",)),
    ("stockholders_equity", "balance", ("Stockholders Equity", "Common Stock Equity")),
    ("retained_earnings", "balance", ("Retained Earnings",)),
    ("cash", "balance", ("Cash And Cash Equivalents",)),
    ("shares_outstanding", "balance", ("Ordinary Shares Number", "Share Issued")),
    ("operating_cash_flow", "cashflow", ("Operating Cash Flow",)),
    ("free_cash_flow", "cashflow", ("Free Cash Flow",)),
    ("stock_based_comp", "cashflow", ("Stock Based Compensation",)),
    ("working_capital", "balance", ("Working Capital",)),
)

_KEY_STATISTICS_FIELDS: tuple[tuple[str, str], ...] = (
    ("current_price", "currentPrice"),
    ("market_cap", "marketCap"),
    ("trailing_pe", "trailingPE"),
    ("enterprise_to_ebitda", "enterpriseToEbitda"),
    ("price_to_sales_ttm", "priceToSalesTrailing12Months"),
    ("price_to_book", "priceToBook"),
    ("revenue_growth", "revenueGrowth"),
    ("beta", "beta"),
    ("total_debt", "totalDebt"),
    ("total_cash", "totalCash"),
    ("ebitda", "ebitda"),
    ("free_cashflow", "freeCashflow"),
    ("operating_cashflow", "operatingCashflow"),
    ("target_mean_price", "targetMeanPrice"),
    ("target_high_price", "targetHighPrice"),
    ("target_low_price", "targetLowPrice"),
)


def _finite(value: Any) -> float | None:
    """A finite number, or None. Yahoo marks missing values with None, NaN, 'Infinity' or a bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _optional_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _is_empty(frame: pd.DataFrame | None) -> bool:
    return frame is None or frame.empty


def _require_columns(
    frame: pd.DataFrame, columns: Sequence[str], symbol: str, dataset: str
) -> None:
    absent = [c for c in columns if c not in frame.columns]
    if absent:
        raise YahooDataError(
            symbol, dataset, f"missing columns {absent}, got {list(frame.columns)}"
        )


def _line(frame: pd.DataFrame, labels: tuple[str, ...], column: pd.Timestamp) -> float | None:
    for label in labels:
        if label not in frame.index:
            continue
        row = frame.loc[label]
        value = row.iloc[0][column] if isinstance(row, pd.DataFrame) else row[column]
        if pd.notna(value):
            return _finite(value)
    return None


def _columns_by_year(frame: pd.DataFrame, symbol: str, dataset: str) -> dict[int, pd.Timestamp]:
    by_year: dict[int, pd.Timestamp] = {}
    for column in frame.columns:
        if not isinstance(column, pd.Timestamp):
            raise YahooDataError(symbol, dataset, f"expected dated columns, got {column!r}")
        if column.year in by_year:
            raise YahooDataError(symbol, dataset, f"two fiscal years end in {column.year}")
        by_year[column.year] = column
    return by_year


class YahooFundamentals:
    """Typed access to Yahoo's company data for one symbol at a time, plus bulk prices."""

    def __init__(
        self, ticker_factory: TickerFactory = yf.Ticker, downloader: Downloader = yf.download
    ) -> None:
        self._ticker = ticker_factory
        self._download = downloader

    def _call(self, symbol: str, dataset: str, fetch: Callable[[], Any]) -> Any:
        try:
            return fetch()
        except _YFINANCE_ERRORS as exc:
            raise YahooDataError(symbol, dataset, f"{type(exc).__name__}: {exc}") from exc

    def key_statistics(self, symbol: Symbol.Input) -> KeyStatistics:
        name = str(Symbol(symbol) if not isinstance(symbol, Symbol) else symbol)
        info = self._call(name, "info", lambda: self._ticker(name).get_info())
        if not isinstance(info, dict):
            raise YahooDataError(name, "info", f"expected a dict, got {type(info).__name__}")
        values = {field: _finite(info.get(key)) for field, key in _KEY_STATISTICS_FIELDS}
        return KeyStatistics(**values, quote_type=_optional_str(info.get("quoteType")))

    def recommendation_counts(self, symbol: Symbol.Input) -> RecommendationCounts | None:
        """The latest month's analyst ratings, or None when no analyst covers the symbol."""
        name = str(Symbol(symbol) if not isinstance(symbol, Symbol) else symbol)
        frame = self._call(name, "recommendations", lambda: self._ticker(name).recommendations)
        if _is_empty(frame):
            return None
        _require_columns(frame, _RECOMMENDATION_COLUMNS, name, "recommendations")
        latest = frame.iloc[0]
        return RecommendationCounts(
            strong_buy=int(latest["strongBuy"]),
            buy=int(latest["buy"]),
            hold=int(latest["hold"]),
            sell=int(latest["sell"]),
            strong_sell=int(latest["strongSell"]),
        )

    def annual_statements(self, symbol: Symbol.Input) -> tuple[AnnualStatement, ...]:
        """Fiscal years present in all three statements, newest first; empty for funds."""
        name = str(Symbol(symbol) if not isinstance(symbol, Symbol) else symbol)
        ticker = self._ticker(name)
        frames = {
            "income": self._call(name, "income_stmt", lambda: ticker.income_stmt),
            "balance": self._call(name, "balance_sheet", lambda: ticker.balance_sheet),
            "cashflow": self._call(name, "cashflow", lambda: ticker.cashflow),
        }
        if any(_is_empty(frame) for frame in frames.values()):
            return ()
        years = {kind: _columns_by_year(frame, name, kind) for kind, frame in frames.items()}
        common = sorted(
            set(years["income"]) & set(years["balance"]) & set(years["cashflow"]), reverse=True
        )
        return tuple(
            AnnualStatement(
                fiscal_year_end=years["income"][year].date(),
                **{
                    field: _line(frames[kind], labels, years[kind][year])
                    for field, kind, labels in _STATEMENT_LINES
                },
            )
            for year in common
        )

    def earnings_dates(self, symbol: Symbol.Input, limit: int = 12) -> tuple[EarningsDate, ...]:
        """Scheduled and reported quarters, newest first; empty when Yahoo has none (funds)."""
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        name = str(Symbol(symbol) if not isinstance(symbol, Symbol) else symbol)
        frame = self._call(
            name, "earnings_dates", lambda: self._ticker(name).get_earnings_dates(limit=limit)
        )
        if _is_empty(frame):
            return ()
        _require_columns(frame, _EARNINGS_COLUMNS, name, "earnings_dates")
        dates = []
        for stamp, row in frame.iterrows():
            if not isinstance(stamp, pd.Timestamp) or stamp.tzinfo is None:
                raise YahooDataError(
                    name, "earnings_dates", f"expected timezone-aware dates, got {stamp!r}"
                )
            dates.append(
                EarningsDate(
                    announced=stamp.to_pydatetime(),
                    eps_estimate=_finite(row["EPS Estimate"]),
                    reported_eps=_finite(row["Reported EPS"]),
                    surprise_pct=_finite(row["Surprise(%)"]),
                )
            )
        return tuple(sorted(dates, key=lambda d: d.announced, reverse=True))

    def rating_changes(self, symbol: Symbol.Input) -> tuple[RatingChange, ...]:
        """Every analyst rating action Yahoo lists, newest first; empty without analyst coverage."""
        name = str(Symbol(symbol) if not isinstance(symbol, Symbol) else symbol)
        frame = self._call(
            name, "upgrades_downgrades", lambda: self._ticker(name).upgrades_downgrades
        )
        if _is_empty(frame):
            return ()
        _require_columns(frame, _RATING_COLUMNS, name, "upgrades_downgrades")
        has_target_action = "priceTargetAction" in frame.columns
        changes = []
        for stamp, row in frame.iterrows():
            if not isinstance(stamp, pd.Timestamp):
                raise YahooDataError(
                    name, "upgrades_downgrades", f"expected dated rows, got {stamp!r}"
                )
            changes.append(
                RatingChange(
                    day=stamp.date(),
                    firm=str(row["Firm"]),
                    action=str(row["Action"]),
                    from_grade=str(row["FromGrade"]),
                    to_grade=str(row["ToGrade"]),
                    price_target_action=_optional_str(row["priceTargetAction"])
                    if has_target_action
                    else None,
                )
            )
        return tuple(sorted(changes, key=lambda c: c.day, reverse=True))

    def bulk_prices(self, symbols: Sequence[Symbol.Input], period: HistoryPeriod) -> BulkPrices:
        """Adjusted daily closes and volumes in one request.

        Symbols without prices are listed in `missing`.

        Rows where no symbol has a close (Yahoo's holiday placeholders) are dropped.
        """
        names = [str(Symbol(s) if not isinstance(s, Symbol) else s) for s in symbols]
        if not names:
            raise ValueError("symbols must not be empty")
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate symbols: {names}")
        label = ",".join(names[:3]) + ("..." if len(names) > 3 else "")
        data = self._call(
            label,
            "download",
            lambda: self._download(
                names,
                period=period.value,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            ),
        )
        if _is_empty(data):
            raise YahooDataError(label, "download", "no prices returned for any symbol")
        if not isinstance(data.columns, pd.MultiIndex):
            raise YahooDataError(label, "download", "expected one column group per symbol")
        returned = set(data.columns.get_level_values(0))
        closes: dict[str, pd.Series] = {}
        volumes: dict[str, pd.Series] = {}
        for name in names:
            if name not in returned:
                continue
            frame = data[name]
            _require_columns(frame, ("Close", "Volume"), name, "download")
            if frame["Close"].isna().all():
                continue  # yfinance keeps a failed symbol as an all-NaN column group
            closes[name] = frame["Close"]
            volumes[name] = frame["Volume"]
        close_frame = pd.DataFrame(closes).dropna(how="all")
        return BulkPrices(
            closes=close_frame,
            volumes=pd.DataFrame(volumes).reindex(close_frame.index),
            missing=tuple(n for n in names if n not in closes),
        )
