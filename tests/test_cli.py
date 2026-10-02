import io
from datetime import date, datetime
from unittest.mock import patch

import pytest
from pydantic_market_data.models import OHLCV, Currency, History, Price, Security, Symbol

from py_yfinance.cli import app
from py_yfinance.source import SearchResult

APPLE = SearchResult(
    symbol=Symbol("AAPL"),
    name="Apple Inc.",
    exchange="NMS",
    currency=Currency("USD"),
    price=Price(150.0),
)


def history_of(*days: int) -> History:
    return History(
        security=Security(symbol=Symbol("AAPL"), name="AAPL"),
        candles=[
            OHLCV(
                date=datetime(2024, 1, d),
                open=100.0,
                high=110.0,
                low=90.0,
                close=100.0 + d,
                volume=1000.0,
            )
            for d in days
        ],
    )


@patch("py_yfinance.cli.source.resolve", return_value=APPLE)
def test_lookup_returns_the_resolved_security(mock_resolve):
    env = app.call("lookup", {"symbol": "AAPL"})

    assert env.exit_code == 0
    assert env.data["symbol"] == "AAPL"
    assert env.data["price"] == 150.0


@patch("py_yfinance.cli.source.resolve", return_value=None)
def test_lookup_not_found(mock_resolve):
    env = app.call("lookup", {"symbol": "NONEXISTENT"})

    assert env.exit_code == 5
    assert env.error.code == "NOT_FOUND"


@patch("py_yfinance.cli.source.resolve", return_value=None)
def test_lookup_builds_the_query(mock_resolve):
    app.call(
        "lookup",
        {"symbol": "AAPL", "price": 185.0, "date": "2024-01-02", "asset_class": "equity"},
    )

    criteria = mock_resolve.call_args.args[0]
    assert criteria.asset_class.value == "equity"
    assert [p.date for p in criteria.price_on] == [date(2024, 1, 2)]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"symbol": "AAPL", "price": 150.0},
        {"symbol": "AAPL", "date": "2024-01-02"},
        {"symbol": "AAPL", "price": 150.0, "date": "not-a-date"},
        {"symbol": "AAPL", "asset_class": "stock"},
        {"symbol": "AAPL", "asset_class": "Equity"},
        {"symbol": "AAPL", "limit": 3},
        {"symbol": "AAPL", "country": "US"},
    ],
)
@patch("py_yfinance.cli.source.resolve")
def test_lookup_rejects_bad_arguments_before_running(mock_resolve, arguments):
    env = app.call("lookup", arguments)

    assert env.exit_code == 2
    assert env.error.phase == "validation"
    mock_resolve.assert_not_called()


@patch("py_yfinance.cli.source.history", return_value=history_of(2, 3))
@patch("py_yfinance.cli.source.resolve", return_value=APPLE)
def test_history_resolves_an_isin_first(mock_resolve, mock_history):
    env = app.call("history", {"isin": "US0378331005", "period": "5d"})

    assert env.exit_code == 0
    assert mock_history.call_args.args[0] == Symbol("AAPL")
    assert [c["close"] for c in env.data["candles"]] == [102.0, 103.0]


@patch("py_yfinance.cli.source.history", return_value=history_of())
def test_history_with_no_candles_is_not_found(mock_history):
    env = app.call("history", {"symbol": "AAPL"})

    assert env.exit_code == 5
    assert env.error.code == "NOT_FOUND"


@pytest.mark.parametrize("arguments", [{}, {"symbol": "AAPL", "price": 150.0}])
@patch("py_yfinance.cli.source.history")
def test_history_rejects_bad_arguments_before_running(mock_history, arguments):
    env = app.call("history", arguments)

    assert env.exit_code == 2
    mock_history.assert_not_called()


@patch("py_yfinance.cli.source.history", return_value=history_of(2, 3))
def test_history_plain_is_a_table(mock_history):
    out = io.StringIO()
    argv = ["history", "--symbol", "AAPL", "--format", "plain"]

    code = app.run(argv, stdout=out, stderr=io.StringIO(), env={}, isatty=False)

    lines = out.getvalue().splitlines()
    assert code == 0
    assert lines[0] == "Symbol: AAPL"
    assert lines[2].startswith("2024-01-02") and lines[2].split()[4] == "102.00"


@patch(
    "py_yfinance.cli.source.search",
    return_value=[
        Security(symbol=Symbol("TSLA"), name="Tesla, Inc."),
        Security(symbol=Symbol("ATSLA"), name="A Tesla fund"),
    ],
)
def test_search_keeps_relevance_order(mock_search):
    env = app.call("search", {"query": "tesla"})

    assert env.exit_code == 0
    assert [r["symbol"] for r in env.data] == ["TSLA", "ATSLA"]


@patch("py_yfinance.cli.source.search", return_value=[])
def test_search_with_no_results_is_empty(mock_search):
    env = app.call("search", {"query": "zzz"})

    assert env.exit_code == 0
    assert env.data == []


@pytest.mark.parametrize("value", ["01/02/2025", "15.01.2025", "Jan 15 2025"])
@patch("py_yfinance.cli.source.resolve", return_value=APPLE)
def test_lookup_rejects_ambiguous_date_formats(mock_resolve, value):
    env = app.call("lookup", {"symbol": "AAPL", "price": 185.0, "date": value})

    assert env.exit_code == 2
    assert env.error.errors[0]["field"] == "date"
    mock_resolve.assert_not_called()
