# Changelog

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

