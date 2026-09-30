import io
import unittest
from contextlib import redirect_stdout
from datetime import date
from unittest.mock import MagicMock, patch

from pydantic_market_data.models import AssetClass, Currency, History, Price, Security, Symbol

from py_yfinance.cli import ExitCode, HistoryCommand, LookupCommand, SearchCommand
from py_yfinance.source import SearchResult


class TestCLI(unittest.TestCase):
    @patch("py_yfinance.cli.source.resolve")
    def test_lookup_command_success(self, mock_resolve):
        mock_result = SearchResult(
            symbol=Symbol("AAPL"),
            name="Apple Inc.",
            exchange="NMS",
            currency=Currency("USD"),
            price=Price(150.0),
        )
        mock_resolve.return_value = mock_result

        cmd = LookupCommand(symbol="AAPL", format="text", report_price=True)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.cli_cmd()

        output = f.getvalue()
        self.assertIn("Symbol: AAPL", output)
        self.assertIn("Name: Apple Inc.", output)
        self.assertIn("Price: 150.00 USD", output)

    @patch("py_yfinance.cli.source.resolve")
    def test_lookup_command_not_found(self, mock_resolve):
        mock_resolve.return_value = None
        cmd = LookupCommand(symbol="NONEXISTENT")

        with self.assertRaises(SystemExit) as cm:
            cmd.cli_cmd()
        self.assertEqual(cm.exception.code, ExitCode.NOT_FOUND)

    @patch("py_yfinance.cli.source.resolve")
    def test_lookup_command_usage_errors(self, mock_resolve):
        cases = [
            {"symbol": "AAPL", "price": 150.0},
            {"symbol": "AAPL", "date": "2024-01-02"},
            {"symbol": "AAPL", "price": 150.0, "date": "not-a-date"},
            {"symbol": "AAPL", "asset_class": "stock"},
            {"symbol": "AAPL", "format": "yaml"},
            {"symbol": "AAPL", "country": "US"},
            {},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SystemExit) as cm:
                    LookupCommand(**kwargs).cli_cmd()
                self.assertEqual(cm.exception.code, ExitCode.USAGE)
        mock_resolve.assert_not_called()

    @patch("py_yfinance.cli.source.resolve")
    def test_lookup_command_builds_query(self, mock_resolve):
        mock_resolve.return_value = None
        cmd = LookupCommand(symbol="AAPL", price=150.0, date="2024-01-02", asset_class="Equity")

        with self.assertRaises(SystemExit):
            cmd.cli_cmd()

        criteria = mock_resolve.call_args.args[0]
        self.assertEqual(criteria.asset_class, AssetClass.EQUITY)
        self.assertEqual(len(criteria.price_on), 1)
        self.assertEqual(criteria.price_on[0].date, date(2024, 1, 2))

    @patch("py_yfinance.cli.source.search")
    def test_search_command_json_empty(self, mock_search):
        mock_search.return_value = []
        f = io.StringIO()
        with redirect_stdout(f):
            SearchCommand(query="zzz", format="json").cli_cmd()
        self.assertEqual(f.getvalue().strip(), "[]")

    @patch("py_yfinance.cli.source.history")
    @patch("py_yfinance.cli.source.resolve")
    def test_history_command_resolves_isin(self, mock_resolve, mock_history):
        mock_resolve.return_value = SearchResult(symbol=Symbol("AAPL"), name="Apple Inc.")
        mock_history.return_value = History(
            security=Security(symbol=Symbol("AAPL"), name="AAPL"), candles=[]
        )

        with self.assertRaises(SystemExit) as cm:
            HistoryCommand(isin="US0378331005").cli_cmd()

        self.assertEqual(cm.exception.code, ExitCode.NOT_FOUND)
        self.assertEqual(mock_history.call_args.args[0], Symbol("AAPL"))

    @patch("py_yfinance.cli.source.history")
    def test_history_command_usage_errors(self, mock_history):
        for kwargs in ({}, {"symbol": "AAPL", "price": 150.0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SystemExit) as cm:
                    HistoryCommand(**kwargs).cli_cmd()
                self.assertEqual(cm.exception.code, ExitCode.USAGE)
        mock_history.assert_not_called()

    @patch("py_yfinance.cli.source.history")
    def test_history_command_json(self, mock_history):
        mock_hist = MagicMock()
        mock_hist.model_dump_json.return_value = '{"security": {"symbol": "AAPL"}, "candles": []}'
        mock_history.return_value = mock_hist

        cmd = HistoryCommand(symbol="AAPL", format="json")
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.cli_cmd()

        output = f.getvalue()
        self.assertIn('{"security": {"symbol": "AAPL"}, "candles": []}', output)


if __name__ == "__main__":
    unittest.main()
