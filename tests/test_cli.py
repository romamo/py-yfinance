import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from pydantic_market_data.models import Currency, Price, Symbol

from py_yfinance.cli import HistoryCommand, LookupCommand
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
        self.assertEqual(cm.exception.code, 1)

    @patch("py_yfinance.cli.source.resolve")
    def test_lookup_command_price_verification_error(self, mock_resolve):
        from datetime import date

        from pydantic_market_data.models import PriceVerificationError

        mock_resolve.side_effect = PriceVerificationError(
            "Test Error", symbol="AAPL", actual_date=date(2024, 1, 1), expected_price=100.0
        )
        cmd = LookupCommand(symbol="AAPL", price=150.0)

        with self.assertRaises(SystemExit) as cm:
            cmd.cli_cmd()
        self.assertEqual(cm.exception.code, 1)

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
