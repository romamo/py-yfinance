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
        # Using str() or .root because result.symbol is a Symbol VO
        self.assertEqual(str(result.symbol), "AAPL")
        self.assertIn("Apple", result.name)

    def test_live_history(self):
        hist = self.source.history("AAPL", period=HistoryPeriod.D1)
        self.assertIsNotNone(hist)
        self.assertEqual(str(hist.security.symbol), "AAPL")
        self.assertGreater(len(hist.candles), 0)


if __name__ == "__main__":
    unittest.main()
