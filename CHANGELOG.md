# Changelog

## [0.1.14] - 2026-04-14

### Fixed
- **Linting**: Resolved missing `Security` import and fixed long lines in CLI and source code identified by `ruff`.

## [0.1.13] - 2026-04-14

### Changed
- **Breaking**: Replaced `Ticker` with `Symbol` and `Security` models to align with `pydantic-market-data>=0.2.0`.
- **Breaking**: Renamed CLI argument `--ticker` to `--symbol` (inherited from `pydantic-market-data`).
- **Source**: Updated `YFinanceDataSource` method signatures and internal logic to use `Symbol` and `Security` types.
- **Search**: `search` and `lookup` now return a list of `Security` objects instead of `Symbol`.
- **History**: `history` now returns a `History` object containing a `Security` instead of just a `Symbol`.

## [0.1.12] - 2026-04-14

### Fixed
- **Protocol**: Renamed `as_of` parameter to `date` in `YFinanceDataSource.get_price` to fully align with the `DataSource` protocol.
- **Internal**: Refactored `src/py_yfinance/source.py` to use `datetime.date` and `datetime.timedelta`, resolving shadowing issues with the renamed `date` parameter.

## [0.1.11] - 2026-04-04

### Fixed
- **Dependencies**: Updated `pydantic-market-data` to `>=0.1.17` to fix missing `asset_class` in `SecurityCriteria`.
- **Packaging**: Removed tracked `.DS_Store` and updated `.gitignore` for better repository hygiene.

## [0.1.10] - 2026-04-03

### Fixed
- **Packaging**: Remove local path dependency for `pydantic-market-data` to ensure PyPI compatibility.


## [0.1.9] - 2026-04-03

### Added
- **Search**: Support for `asset_class` filtering in `YFinanceDataSource.resolve`.
- **Validation**: Strict validation for asset class names (CRYPTO, STOCK, ETF, INDEX).


## [0.1.8] - 2026-03-27

### Changed
- **Core**: Improved `PriceVerificationError` handling to be more descriptive.
- **Data Source**: Enhanced `YFinanceDataSource` to gracefully handle empty data and add source metadata to errors.

## [0.1.7] - 2026-02-19

### Fixed
- **CI**: Sync formatting and merged recent status fixes.

## [0.1.6] - 2026-02-19

### Fixed
- **Release**: Re-release of v0.1.5 fixes due to PyPI upload conflict.

## [0.1.5] - 2026-02-19

### Fixed
- **Linting**: Fixed various lint errors (bare exceptions, line lengths) identified by `ruff`.

## [0.1.4] - 2026-02-19

### Fixed
- **Documentation**: Removed incorrect references to "Typer CLI" and `[cli]` extra in `README.md`.
- **Tests**: Fixed `test_resolve.py` mocking to correctly handle internal `yfinance` attributes.
- **Dependencies**: Clarified that `argparse` is used for the CLI, requiring no extra dependencies.

