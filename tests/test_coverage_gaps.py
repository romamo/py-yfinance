from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pydantic_market_data.models import Price, Symbol

from py_yfinance.cli import AppCLI, HistoryCommand, LookupCommand
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


def test_cli_lookup_json(source):
    cmd = LookupCommand(symbol="AAPL", format="json")
    with patch("py_yfinance.cli.source.resolve") as mock_resolve:
        mock_resolve.return_value = MagicMock(
            symbol="AAPL",
            name="Apple",
            exchange="NSQ",
            currency="USD",
            price=Price(150.0),
        )
        mock_resolve.return_value.model_dump_json.return_value = '{"symbol": "AAPL"}'

        with patch("builtins.print") as mock_print:
            cmd.cli_cmd()
            mock_print.assert_called_with('{"symbol": "AAPL"}')


def test_cli_history_text(source):
    cmd = HistoryCommand(symbol="AAPL", format="text")
    with patch("py_yfinance.cli.source.history") as mock_history:
        mock_history.return_value = MagicMock(
            security=MagicMock(symbol="AAPL"), candles=[MagicMock(date="2024-01-01", close=150.0)]
        )
        with patch("builtins.print") as mock_print:
            cmd.cli_cmd()
            # Check if print was called with essential info
            calls = [call.args[0] for call in mock_print.call_args_list]
            assert any("Symbol: AAPL" in s for s in calls)
            assert any("Last Candle" in s for s in calls)


def test_app_cli_logging_setup():
    app = AppCLI.model_construct(v=True)
    app.lookup = MagicMock()
    app.history = None

    with patch("py_yfinance.cli.setup_logging") as mock_setup:
        with patch("pydantic_settings.CliApp.run_subcommand"):
            app.cli_cmd()
            mock_setup.assert_called()


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


def test_cli_app_main():
    with patch("pydantic_settings.CliApp.run") as mock_run:
        from py_yfinance.cli import main

        main()
        mock_run.assert_called_with(AppCLI)
