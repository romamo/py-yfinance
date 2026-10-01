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
        df = pd.DataFrame([{"Close": 0.0, "Low": 0.0, "High": 0.0}], index=[pd.Timestamp.now()])
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        result = source._validate_candidate_data(Symbol("AAPL"))
        assert result is None


def test_get_price_with_date(source):
    target_date = date(2024, 1, 1)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_t = MagicMock()
        df = pd.DataFrame([{"Close": 150.0}], index=[pd.Timestamp(target_date)])
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
            [{"Close": 150.0, "Low": 140.0, "High": 160.0}],
            index=[pd.Timestamp.now()],
        )
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        from pydantic_market_data.models import PriceVerificationError

        with pytest.raises(PriceVerificationError):
            source._validate_candidate_data(Symbol("AAPL"), target_price=Price(200.0))
