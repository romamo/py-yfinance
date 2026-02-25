import logging
import unittest

from py_yfinance.logging_utils import setup_logging


class TestLoggingUtils(unittest.TestCase):
    def test_setup_logging_default(self):
        setup_logging(v=False, vv=False)
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.WARNING)

    def test_setup_logging_verbose(self):
        setup_logging(v=True, vv=False)
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.INFO)

    def test_setup_logging_debug(self):
        setup_logging(v=False, vv=True)
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.DEBUG)

    def test_setup_logging_silence_loggers(self):
        setup_logging(v=False, vv=False, silence_loggers=["test_noisy"])
        self.assertEqual(logging.getLogger("test_noisy").getEffectiveLevel(), logging.WARNING)

if __name__ == "__main__":
    unittest.main()
