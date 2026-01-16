from py_yfinance import YFinanceDataSource


def test_smoke():
    assert YFinanceDataSource
    print("Smoke test passed: YFinanceDataSource imported successfully.")

if __name__ == "__main__":
    test_smoke()
