"""YahooFundamentals against fake yfinance objects passed through its constructor (no patching)."""

import datetime
import math
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError
from pydantic_market_data.models import HistoryPeriod
from yfinance import exceptions as yf_exceptions  # type: ignore

from py_yfinance import KeyStatistics, YahooDataError, YahooFundamentals

FY = [pd.Timestamp("2026-06-30"), pd.Timestamp("2025-06-30")]


class FakeTicker:
    def __init__(self, **datasets: Any) -> None:
        self._datasets = datasets

    def _get(self, name: str) -> Any:
        value = self._datasets.get(name)
        if isinstance(value, Exception):
            raise value
        return value

    def get_info(self) -> dict[str, Any]:
        return self._get("info")

    @property
    def recommendations(self) -> pd.DataFrame | None:
        return self._get("recommendations")

    @property
    def income_stmt(self) -> pd.DataFrame | None:
        return self._get("income_stmt")

    @property
    def balance_sheet(self) -> pd.DataFrame | None:
        return self._get("balance_sheet")

    @property
    def cashflow(self) -> pd.DataFrame | None:
        return self._get("cashflow")

    @property
    def upgrades_downgrades(self) -> pd.DataFrame | None:
        return self._get("upgrades_downgrades")

    def get_earnings_dates(self, limit: int) -> pd.DataFrame | None:
        self.earnings_limit = limit
        return self._get("earnings_dates")


def _source(ticker: FakeTicker) -> YahooFundamentals:
    return YahooFundamentals(ticker_factory=lambda symbol: ticker)


def _statement(rows: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=FY).T


def _statements() -> FakeTicker:
    return FakeTicker(
        income_stmt=_statement(
            {
                "Total Revenue": [100.0, 80.0],
                "Operating Income": [30.0, 20.0],
                "Net Income": [20.0, 15.0],
                "Normalized EBITDA": [40.0, 30.0],
            }
        ),
        balance_sheet=_statement(
            {
                "Total Assets": [500.0, 450.0],
                "Common Stock Equity": [300.0, 280.0],
                "Ordinary Shares Number": [10.0, math.nan],
                "Share Issued": [11.0, 12.0],
            }
        ),
        cashflow=_statement({"Operating Cash Flow": [35.0, 25.0], "Free Cash Flow": [25.0, 18.0]}),
    )


def test_key_statistics_keeps_finite_numbers_only() -> None:
    info = {
        "currentPrice": 525.18,
        "marketCap": 3_899_747_991_552,
        "trailingPE": "Infinity",
        "priceToBook": math.nan,
        "beta": True,
        "targetMeanPrice": 582.6,
        "quoteType": "EQUITY",
    }
    stats = _source(FakeTicker(info=info)).key_statistics("MSFT")
    assert stats.current_price == 525.18
    assert stats.market_cap == 3_899_747_991_552
    assert stats.trailing_pe is None
    assert stats.price_to_book is None
    assert stats.beta is None
    assert stats.target_mean_price == 582.6
    assert stats.quote_type == "EQUITY"


def test_key_statistics_wraps_yfinance_errors() -> None:
    ticker = FakeTicker(info=yf_exceptions.YFException("rate limited"))
    with pytest.raises(YahooDataError, match="MSFT: info: YFException: rate limited"):
        _source(ticker).key_statistics("MSFT")


def test_key_statistics_rejects_non_dict() -> None:
    with pytest.raises(YahooDataError, match="expected a dict"):
        _source(FakeTicker(info=["not", "a", "dict"])).key_statistics("MSFT")


def test_recommendation_counts_reads_latest_month() -> None:
    frame = pd.DataFrame(
        {
            "period": ["0m", "-1m"],
            "strongBuy": [10, 9],
            "buy": [20, 19],
            "hold": [5, 6],
            "sell": [1, 1],
            "strongSell": [0, 0],
        }
    )
    counts = _source(FakeTicker(recommendations=frame)).recommendation_counts("MSFT")
    assert counts is not None
    assert (counts.strong_buy, counts.buy, counts.hold, counts.sell, counts.strong_sell) == (
        10,
        20,
        5,
        1,
        0,
    )


def test_recommendation_counts_none_without_coverage() -> None:
    assert (
        _source(FakeTicker(recommendations=pd.DataFrame())).recommendation_counts("VWRA.L") is None
    )


def test_recommendation_counts_rejects_unknown_shape() -> None:
    with pytest.raises(YahooDataError, match="missing columns"):
        _source(FakeTicker(recommendations=pd.DataFrame({"x": [1]}))).recommendation_counts("MSFT")


def test_annual_statements_newest_first_with_label_fallbacks() -> None:
    statements = _source(_statements()).annual_statements("MSFT")
    assert [s.fiscal_year_end for s in statements] == [
        datetime.date(2026, 6, 30),
        datetime.date(2025, 6, 30),
    ]
    current, previous = statements
    assert current.revenue == 100.0
    assert current.ebit == 30.0  # "Operating Income" when "EBIT" is absent
    assert current.ebitda == 40.0  # "Normalized EBITDA" when "EBITDA" is absent
    assert current.stockholders_equity == 300.0
    assert current.shares_outstanding == 10.0
    assert (
        previous.shares_outstanding == 12.0
    )  # NaN under the first label falls through to "Share Issued"
    assert current.gross_profit is None


def test_annual_statements_only_years_in_all_three() -> None:
    ticker = _statements()
    ticker._datasets["cashflow"] = pd.DataFrame({"Operating Cash Flow": [35.0]}, index=FY[:1]).T
    assert [s.fiscal_year_end.year for s in _source(ticker).annual_statements("MSFT")] == [2026]


def test_annual_statements_empty_for_funds() -> None:
    ticker = FakeTicker(
        income_stmt=pd.DataFrame(), balance_sheet=pd.DataFrame(), cashflow=pd.DataFrame()
    )
    assert _source(ticker).annual_statements("VWRA.L") == ()


def test_annual_statements_rejects_undated_columns() -> None:
    ticker = _statements()
    ticker._datasets["income_stmt"] = pd.DataFrame({"2026": [1.0]}, index=["Total Revenue"])
    with pytest.raises(YahooDataError, match="expected dated columns"):
        _source(ticker).annual_statements("MSFT")


def _earnings() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        ["2026-07-29 16:00", "2026-10-28 16:00"],
        name="Earnings Date",
    ).tz_localize("America/New_York")
    return pd.DataFrame(
        {
            "EPS Estimate": [4.24, 4.72],
            "Reported EPS": [4.74, math.nan],
            "Surprise(%)": [11.81, math.nan],
        },
        index=index,
    )


def test_earnings_dates_newest_first_with_upcoming_report() -> None:
    ticker = FakeTicker(earnings_dates=_earnings())
    dates = _source(ticker).earnings_dates("MSFT", limit=6)
    assert ticker.earnings_limit == 6
    assert [d.announced.date() for d in dates] == [
        datetime.date(2026, 10, 28),
        datetime.date(2026, 7, 29),
    ]
    upcoming, reported = dates
    assert upcoming.reported_eps is None and upcoming.surprise_pct is None
    assert reported.surprise_pct == 11.81
    assert reported.announced.tzinfo is not None


def test_earnings_dates_empty_when_yahoo_has_none() -> None:
    assert _source(FakeTicker(earnings_dates=None)).earnings_dates("VWRA.L") == ()


def test_earnings_dates_rejects_naive_dates() -> None:
    frame = _earnings()
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(YahooDataError, match="timezone-aware"):
        _source(FakeTicker(earnings_dates=frame)).earnings_dates("MSFT")


def test_earnings_dates_rejects_bad_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        _source(FakeTicker()).earnings_dates("MSFT", limit=0)


def test_earnings_dates_wraps_missing_lxml() -> None:
    # yfinance raises ImportError without lxml; that is an install problem, not a data problem
    ticker = FakeTicker(earnings_dates=ImportError("`Import lxml` failed."))
    with pytest.raises(ImportError, match="lxml"):
        _source(ticker).earnings_dates("MSFT")


def test_rating_changes() -> None:
    frame = pd.DataFrame(
        {
            "Firm": ["Oppenheimer", "Bernstein"],
            "ToGrade": ["Outperform", "Market Perform"],
            "FromGrade": ["Outperform", "Outperform"],
            "Action": ["main", "down"],
            "priceTargetAction": ["Raises", math.nan],
        },
        index=pd.DatetimeIndex(["2026-09-25 12:00", "2026-09-21 09:00"], name="GradeDate"),
    )
    changes = _source(FakeTicker(upgrades_downgrades=frame)).rating_changes("MSFT")
    assert [c.day for c in changes] == [datetime.date(2026, 9, 25), datetime.date(2026, 9, 21)]
    assert changes[0].price_target_action == "Raises"
    assert changes[1].price_target_action is None
    assert changes[1].action == "down"


def test_rating_changes_empty_without_coverage() -> None:
    assert _source(FakeTicker(upgrades_downgrades=pd.DataFrame())).rating_changes("VWRA.L") == ()


def _download(frames: dict[str, pd.DataFrame]) -> Any:
    def download(names: list[str], **kwargs: Any) -> pd.DataFrame:
        download.kwargs = kwargs  # type: ignore[attr-defined]
        return pd.concat({n: frames[n] for n in names}, axis=1)

    return download


def _prices(closes: list[float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(["2026-10-01", "2026-10-02", "2026-10-05"][: len(closes)])
    return pd.DataFrame({"Close": closes, "Volume": [1000.0] * len(closes)}, index=index)


def test_bulk_prices_lists_symbols_without_prices_as_missing() -> None:
    download = _download(
        {
            "MSFT": _prices([520.0, 525.0, 528.0]),
            "NOPE": _prices([math.nan, math.nan, math.nan]),
        }
    )
    bulk = YahooFundamentals(downloader=download).bulk_prices(["MSFT", "NOPE"], HistoryPeriod.Y1)
    assert list(bulk.closes.columns) == ["MSFT"]
    assert bulk.missing == ("NOPE",)
    assert bulk.closes["MSFT"].iloc[-1] == 528.0
    assert list(bulk.volumes.index) == list(bulk.closes.index)
    assert download.kwargs == {  # type: ignore[attr-defined]
        "period": "1y",
        "auto_adjust": True,
        "group_by": "ticker",
        "threads": True,
        "progress": False,
    }


def test_bulk_prices_drops_holiday_placeholder_rows() -> None:
    frame = _prices([520.0, math.nan, 528.0])
    bulk = YahooFundamentals(downloader=_download({"MSFT": frame})).bulk_prices(
        ["MSFT"], HistoryPeriod.Y1
    )
    assert len(bulk.closes) == 2


def test_bulk_prices_raises_when_nothing_returned() -> None:
    source = YahooFundamentals(downloader=lambda names, **kwargs: pd.DataFrame())
    with pytest.raises(YahooDataError, match="no prices returned"):
        source.bulk_prices(["MSFT"], HistoryPeriod.Y1)


@pytest.mark.parametrize("symbols", [[], ["MSFT", "MSFT"]])
def test_bulk_prices_rejects_bad_symbol_lists(symbols: list[str]) -> None:
    with pytest.raises(ValueError):
        YahooFundamentals(downloader=_download({})).bulk_prices(symbols, HistoryPeriod.Y1)


def test_models_are_frozen_and_strict() -> None:
    stats = _source(FakeTicker(info={"currentPrice": 1.0})).key_statistics("MSFT")
    with pytest.raises(ValidationError):
        stats.current_price = 2.0  # type: ignore[misc]
    with pytest.raises(ValidationError, match="bogus"):
        KeyStatistics.model_validate({**stats.model_dump(), "bogus": 1})
    with pytest.raises(ValidationError):
        KeyStatistics.model_validate({**stats.model_dump(), "current_price": math.inf})
