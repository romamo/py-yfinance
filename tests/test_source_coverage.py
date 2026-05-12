import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
from pydantic_market_data.models import AssetClass, Currency, HistoryPeriod, Price, SecurityQuery

from py_yfinance.source import (
    PriceVerificationError,
    ValidatedCandidate,
    YFinanceDataSource,
)


class TestYFinanceDataSourceCoverage(unittest.TestCase):
    def setUp(self):
        self.source = YFinanceDataSource()

    def test_map_country_valid_code(self):
        self.assertEqual(self.source._map_country("US"), "US")

    def test_map_country_valid_name(self):
        self.assertEqual(self.source._map_country("United States"), "US")

    def test_map_country_fuzzy_lookup(self):
        # pycountry.countries.lookup("USA") should find United States
        self.assertEqual(self.source._map_country("USA"), "US")

    def test_map_country_invalid(self):
        self.assertIsNone(self.source._map_country("InvalidCountry"))

    def test_map_country_none(self):
        self.assertIsNone(self.source._map_country(None))

    @patch("py_yfinance.source.Search")
    def test_search_success(self, mock_search):
        mock_instance = MagicMock()
        mock_instance.quotes = [
            {
                "symbol": "AAPL",
                "shortname": "Apple Inc.",
                "exchange": "NMS",
                "country": "United States",
            },
            {"symbol": "MSFT", "longname": "Microsoft", "exchange": "NMS"},
        ]
        mock_search.return_value = mock_instance

        results = self.source.search("Apple")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].symbol.root, "AAPL")
        self.assertEqual(results[0].name, "Apple Inc.")
        self.assertEqual(results[0].country.root, "US")
        self.assertEqual(results[1].symbol.root, "MSFT")
        self.assertEqual(results[1].name, "Microsoft")
        self.assertIsNone(results[1].country)

    @patch("py_yfinance.source.Search")
    def test_search_missing_fields(self, mock_search):
        mock_instance = MagicMock()
        mock_instance.quotes = [
            {"symbol": "AAPL"},  # Missing name, exchange, etc.
            {"shortname": "No Symbol"},  # Missing symbol
        ]
        mock_search.return_value = mock_instance

        results = self.source.search("Apple")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].symbol.root, "AAPL")
        self.assertEqual(results[0].name, "Unknown")

    @patch("yfinance.Lookup")
    def test_lookup_success(self, mock_lookup):
        mock_instance = MagicMock()
        df = pd.DataFrame(
            [
                {"shortName": "Apple Inc.", "exchange": "NMS"},
                {"shortName": "Microsoft", "exchange": "NMS"},
            ],
            index=["AAPL", "MSFT"],
        )
        mock_instance.get_all.return_value = df
        mock_lookup.return_value = mock_instance

        results = self.source.lookup("Apple")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].symbol.root, "AAPL")
        self.assertEqual(results[1].symbol.root, "MSFT")

    @patch("yfinance.Lookup")
    def test_lookup_empty(self, mock_lookup):
        mock_instance = MagicMock()
        mock_instance.get_all.return_value = pd.DataFrame()
        mock_lookup.return_value = mock_instance

        results = self.source.lookup("Empty")
        self.assertEqual(len(results), 0)

    @patch("py_yfinance.source.YFinanceDataSource._validate_candidate_data")
    @patch("py_yfinance.source.YFinanceDataSource._generate_candidates")
    def test_resolve_success(self, mock_gen, mock_val):
        mock_gen.return_value = iter(
            [
                {
                    "symbol": "AAPL",
                    "shortname": "Apple Inc.",
                    "exchange": "NMS",
                    "quoteType": "EQUITY",
                }
            ]
        )
        mock_val.return_value = ValidatedCandidate(price=Price(150.0), currency=Currency("USD"))

        criteria = SecurityQuery(symbol="AAPL")
        result = self.source.resolve(criteria)

        self.assertIsNotNone(result)
        self.assertEqual(result.symbol.root, "AAPL")
        self.assertEqual(result.price.root, 150.0)
        self.assertEqual(result.asset_class, AssetClass.EQUITY)

    @patch("py_yfinance.source.YFinanceDataSource._validate_candidate_data")
    @patch("py_yfinance.source.YFinanceDataSource._generate_candidates")
    def test_resolve_exchange_mismatch(self, mock_gen, mock_val):
        mock_gen.return_value = iter([{"symbol": "AAPL", "exchange": "Frankfurt"}])

        criteria = SecurityQuery(symbol="AAPL", exchange="NASDAQ")
        result = self.source.resolve(criteria)
        self.assertIsNone(result)

    @patch("py_yfinance.source.Search")
    def test_generate_candidates_isin(self, mock_search):
        mock_instance = MagicMock()
        mock_instance.quotes = [{"symbol": "AAPL"}]
        mock_search.return_value = mock_instance

        candidates = list(self.source._generate_candidates(SecurityQuery(isin="US0378331005")))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["symbol"], "AAPL")

    @patch("yfinance.Ticker")
    def test_validate_candidate_data_success(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.iloc = [{"Low": 140.0, "High": 160.0, "Close": 150.0}]
        mock_ticker.history.return_value = pd.DataFrame(mock_hist.iloc)

        mock_price_history = MagicMock()
        mock_price_history._history_metadata = {"currency": "USD"}
        mock_ticker._price_history = mock_price_history
        mock_ticker_class.return_value = mock_ticker

        res = self.source._validate_candidate_data(
            "AAPL", target_date=date(2023, 1, 1), target_price=155.0
        )
        self.assertIsNotNone(res)
        self.assertEqual(res.price.root, 150.0)
        self.assertEqual(res.currency, "USD")

    @patch("yfinance.Ticker")
    def test_validate_candidate_data_price_error(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.iloc = [{"Low": 140.0, "High": 160.0, "Close": 150.0}]
        mock_ticker.history.return_value = pd.DataFrame(mock_hist.iloc)
        mock_ticker_class.return_value = mock_ticker

        with self.assertRaises(PriceVerificationError):
            self.source._validate_candidate_data("AAPL", target_price=200.0)

    @patch("yfinance.Ticker")
    def test_history_success(self, mock_ticker_class):
        mock_ticker = MagicMock()
        df = pd.DataFrame(
            [{"Open": 100.0, "High": 110.0, "Low": 90.0, "Close": 105.0, "Volume": 1000}],
            index=[date(2023, 1, 1)],
        )
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        hist = self.source.history("AAPL", period=HistoryPeriod.D1)
        self.assertEqual(len(hist.candles), 1)
        self.assertEqual(hist.candles[0].close, 105.0)

    @patch("yfinance.Ticker")
    def test_get_price_success(self, mock_ticker_class):
        mock_ticker = MagicMock()
        df = pd.DataFrame([{"Close": 150.0}], index=[date(2023, 1, 1)])
        mock_ticker.history.return_value = df
        mock_ticker_class.return_value = mock_ticker

        price = self.source.get_price("AAPL")
        self.assertEqual(price.root, 150.0)

    @patch("yfinance.Ticker")
    def test_get_price_fast_info_fallback(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()  # Empty history
        mock_fast_info = MagicMock()
        mock_fast_info.last_price = 155.0
        mock_ticker.fast_info = mock_fast_info
        mock_ticker_class.return_value = mock_ticker

        price = self.source.get_price("AAPL")
        self.assertEqual(price.root, 155.0)

    @patch("yfinance.Ticker")
    def test_get_price_failure(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker.fast_info = None
        mock_ticker_class.return_value = mock_ticker

        with self.assertRaises(RuntimeError):
            self.source.get_price("AAPL")

    def test_validate_method(self):
        with patch.object(self.source, "_validate_candidate_data") as mock_val:
            mock_val.return_value = ValidatedCandidate(price=Price(100), currency=Currency("USD"))
            res = self.source.validate("AAPL", date.today(), 100)
            self.assertTrue(res)

            mock_val.return_value = None
            res = self.source.validate("AAPL", date.today(), 100)
            self.assertFalse(res)

    @patch("yfinance.Ticker")
    def test_validate_candidate_data_empty_history(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()  # Empty
        mock_ticker_class.return_value = mock_ticker

        res = self.source._validate_candidate_data("AAPL")
        self.assertIsNone(res)

    @patch("yfinance.Ticker")
    def test_validate_candidate_data_zero_price(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.iloc = [{"Low": 0.0, "High": 0.0, "Close": 0.0}]
        mock_ticker.history.return_value = pd.DataFrame(mock_hist.iloc)
        mock_ticker_class.return_value = mock_ticker

        res = self.source._validate_candidate_data("AAPL")
        self.assertIsNone(res)

    @patch("py_yfinance.source.YFinanceDataSource._validate_candidate_data")
    @patch("py_yfinance.source.YFinanceDataSource._generate_candidates")
    def test_resolve_seen_filtering(self, mock_gen, mock_val):
        # Return same ticker twice
        mock_gen.return_value = iter(
            [
                {"symbol": "AAPL", "exchange": "NMS"},
                {"symbol": "AAPL", "exchange": "NMS"},
                {"symbol": "MSFT", "exchange": "NMS"},
            ]
        )
        # First call returns None (fails validation), second call should be skipped via 'seen',
        # third call returns valid data.
        mock_val.side_effect = [
            None,
            ValidatedCandidate(price=Price(150.0), currency=Currency("USD")),
        ]

        criteria = SecurityQuery(symbol="AAPL")
        result = self.source.resolve(criteria)
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol.root, "MSFT")
        # Should call validate exactly twice: once for the first AAPL, once for MSFT.
        # The second AAPL is skipped via line 151 'continue'.
        self.assertEqual(mock_val.call_count, 2)

    @patch("py_yfinance.source.YFinanceDataSource._validate_candidate_data")
    @patch("py_yfinance.source.YFinanceDataSource._generate_candidates")
    def test_resolve_no_data(self, mock_gen, mock_val):
        mock_gen.return_value = iter([{"symbol": "AAPL"}])
        mock_val.return_value = None

        result = self.source.resolve(SecurityQuery(symbol="AAPL"))
        self.assertIsNone(result)

    @patch("yfinance.Lookup")
    def test_lookup_missing_metadata(self, mock_lookup):
        mock_instance = MagicMock()
        df = pd.DataFrame(
            [
                {"shortName": None, "exchange": None},
            ],
            index=["AAPL"],
        )
        mock_instance.get_all.return_value = df
        mock_lookup.return_value = mock_instance

        results = self.source.lookup("Apple")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Unknown")
        self.assertIsNone(results[0].exchange)


if __name__ == "__main__":
    unittest.main()
