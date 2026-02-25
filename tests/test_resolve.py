import unittest
from unittest.mock import MagicMock, patch

from pydantic_market_data.models import SecurityCriteria

from py_yfinance.source import YFinanceDataSource


class TestYFinanceResolve(unittest.TestCase):
    def setUp(self):
        self.source = YFinanceDataSource()

    @patch("py_yfinance.source.Search")
    @patch("yfinance.Ticker")
    def test_resolve_exact_symbol(self, mock_ticker, mock_search):
        """Test resolving a symbol that exists directly."""
        # Setup mock Search
        mock_search_instance = MagicMock()
        mock_search_instance.quotes = [
            {
                "symbol": "AAPL",
                "shortname": "Apple Inc.",
                "exchange": "NASDAQ",
                "country": "United States",
            }
        ]
        mock_search.return_value = mock_search_instance

        # Setup mock Ticker
        mock_instance = MagicMock()

        # Mock history for validation
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.iloc = MagicMock()
        mock_hist.iloc.__getitem__.return_value = {"Close": 150.0}
        mock_instance.history.return_value = mock_hist

        # Mock history_metadata via internal _price_history
        mock_price_history = MagicMock()
        mock_price_history._history_metadata = {"currency": "USD"}
        mock_instance._price_history = mock_price_history

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
        self.assertEqual(result.ticker.root, "AAPL")
        self.assertEqual(result.name, "Apple Inc.")

        # Ensure Ticker was called with "AAPL"
        mock_ticker.assert_called_with("AAPL")

    @patch("py_yfinance.source.Search")
    @patch("yfinance.Ticker")
    def test_resolve_not_found(self, mock_ticker, mock_search):
        """Test resolving a symbol that doesn't exist."""
        # Setup mock Search
        mock_search_instance = MagicMock()
        mock_search_instance.quotes = []
        mock_search.return_value = mock_search_instance

        # Setup mock Ticker
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
