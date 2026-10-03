from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pydantic_market_data.models import Price, Symbol

from py_yfinance.source import YFinanceDataSource


@pytest.fixture
def source():
    return YFinanceDataSource()


def test_validate_candidate_data_empty_hist(source):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_t

        result = source._validate_candidate_data(Symbol("AAPL"))
        assert result is None


def test_validate_candidate_data_zero_price(source):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        df = pd.DataFrame(
            [{"Open": 0.0, "High": 0.0, "Low": 0.0, "Close": 0.0}], index=[pd.Timestamp.now()]
        )
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        result = source._validate_candidate_data(Symbol("AAPL"))
        assert result is None


def test_get_price_with_date(source):
    target_date = date(2024, 1, 1)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        df = pd.DataFrame(
            [{"Open": 150.0, "High": 150.0, "Low": 150.0, "Close": 150.0}],
            index=[pd.Timestamp(target_date)],
        )
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        price = source.get_price("AAPL", date=target_date)
        assert price.root == 150.0


def test_get_price_with_date_fail(source):
    target_date = date(2024, 1, 1)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_t

        with pytest.raises(RuntimeError, match="Could not retrieve price"):
            source.get_price("AAPL", date=target_date)


def test_validate_candidate_data_price_mismatch(source):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        # Price is 150, but we specify target_price=200
        df = pd.DataFrame(
            [{"Open": 150.0, "High": 160.0, "Low": 140.0, "Close": 150.0}],
            index=[pd.Timestamp.now()],
        )
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        from pydantic_market_data.models import PriceVerificationError

        with pytest.raises(PriceVerificationError):
            source._validate_candidate_data(Symbol("AAPL"), target_price=Price(200.0))


def _bars_with_unpriced_last_session() -> pd.DataFrame:
    """Yahoo's frame for a London listing: the last session has NaN prices, real volume."""
    nan = float("nan")
    return pd.DataFrame(
        [
            {"Open": 122.0, "High": 124.1, "Low": 121.5, "Close": 124.1, "Volume": 101902821},
            {"Open": nan, "High": nan, "Low": nan, "Close": nan, "Volume": 52583695},
        ],
        index=[pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-02")],
    )


def test_validate_candidate_data_skips_unpriced_bar(source):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        mock_t.history.return_value = _bars_with_unpriced_last_session()
        mock_t._price_history._history_metadata = {"currency": "GBp"}
        mock_ticker.return_value = mock_t

        result = source._validate_candidate_data(Symbol("VOD.L"))

        assert result is not None
        assert result.price.root == 124.1


def test_get_price_skips_unpriced_bar(source):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        mock_t.history.return_value = _bars_with_unpriced_last_session()
        mock_ticker.return_value = mock_t

        assert source.get_price("VOD.L").root == 124.1


def test_history_skips_unpriced_bar(source):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        mock_t.history.return_value = _bars_with_unpriced_last_session()
        mock_ticker.return_value = mock_t

        hist = source.history("VOD.L")

        assert [c.close for c in hist.candles] == [124.1]
