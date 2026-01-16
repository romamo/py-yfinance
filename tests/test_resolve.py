import unittest
from unittest.mock import MagicMock, patch

from pydantic_market_data.models import SecurityCriteria

from py_yfinance.source import YFinanceDataSource


class TestYFinanceResolve(unittest.TestCase):
    def setUp(self):
        self.source = YFinanceDataSource()

    @patch("yfinance.Ticker")
    def test_resolve_exact_symbol(self, mock_ticker):
        """Test resolving a symbol that exists directly."""
        # Setup mock
        mock_instance = MagicMock()
        # fast_info must be an object with attributes, not a dict
        mock_fast_info = MagicMock()
        mock_fast_info.last_price = 150.0
        mock_fast_info.currency = "USD"
        mock_instance.fast_info = mock_fast_info

        mock_instance.info = {
            "symbol": "AAPL",
            "longName": "Apple Inc.",
            "exchange": "NASDAQ",
            "country": "United States",
            "currency": "USD",
        }
        mock_ticker.return_value = mock_instance

        criteria = SecurityCriteria(symbol="AAPL")
        result = self.source.resolve(criteria)

        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, "AAPL")
        self.assertEqual(result.name, "Apple Inc.")

        # Ensure Ticker was called with "AAPL"
        mock_ticker.assert_called_with("AAPL")

    @patch("yfinance.Ticker")
    def test_resolve_with_suffix(self, mock_ticker):
        """Test resolving a symbol that needs a suffix appended."""

        def ticker_side_effect(ticker_str):
            mock = MagicMock()
            if ticker_str == "ABC":
                mock.fast_info = MagicMock()
                mock.fast_info.last_price = None  # Invalid
            elif ticker_str == "ABC.DE":
                mock_fast_info = MagicMock()
                mock_fast_info.last_price = 50.0
                mock_fast_info.currency = "EUR"
                mock.fast_info = mock_fast_info

                mock.info = {
                    "symbol": "ABC.DE",
                    "longName": "ABC German Corp",
                    "exchange": "GER",
                    "country": "Germany",
                    "currency": "EUR",
                }
            else:
                mock.fast_info = MagicMock()
                mock.fast_info.last_price = None
            return mock

        mock_ticker.side_effect = ticker_side_effect

        criteria = SecurityCriteria(symbol="ABC", preferred_exchanges=["IBIS"])  # IBIS maps to .DE
        result = self.source.resolve(criteria)

        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, "ABC.DE")

    @patch("yfinance.Ticker")
    def test_resolve_not_found(self, mock_ticker):
        """Test resolving a symbol that doesn't exist."""
        mock_instance = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.last_price = None
        mock_instance.fast_info = mock_fast_info
        mock_ticker.return_value = mock_instance

        criteria = SecurityCriteria(symbol="INVALID")
        result = self.source.resolve(criteria)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
