import unittest

from pydantic_market_data.models import HistoryPeriod, SecurityCriteria

from py_yfinance.source import YFinanceDataSource


class TestYFinanceIntegration(unittest.TestCase):
    """
    Live integration tests against Yahoo Finance API.
    WARNING: Requires network access and may be slow or flaky.
    """

    def setUp(self):
        self.source = YFinanceDataSource()

    def test_live_resolve_aapl(self):
        criteria = SecurityCriteria(symbol="AAPL")
        result = self.source.resolve(criteria)

        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, "AAPL")
        self.assertIn("Apple", result.name)

    def test_live_resolve_suffix_mapping(self):
        # 4GLD on IBIS should map to 4GLD.DE
        criteria = SecurityCriteria(symbol="4GLD", preferred_exchanges=["IBIS"])
        result = self.source.resolve(criteria)

        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, "4GLD.DE")

    def test_live_history(self):
        hist = self.source.history("AAPL", period=HistoryPeriod.D1)
        self.assertIsNotNone(hist)
        self.assertEqual(hist.symbol.ticker, "AAPL")
        self.assertGreater(len(hist.candles), 0)


if __name__ == "__main__":
    unittest.main()
