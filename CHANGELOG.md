# Changelog

## [0.3.1] - 2026-10-02

### Changed
- **Dependencies**: Bumped `pydantic-market-data` to `>=0.7.0`. `lookup --date` and `PriceOnDate.date` now accept only `YYYY-MM-DD`, `YYYY/MM/DD` or `YYYYMMDD`; ambiguous strings such as `01/02/2025` exit `2` instead of being read month-first

### Fixed
- **Docs**: README samples use the current API (`SecurityQuery` with `price_on`, `history --symbol`), install `py-yfinance` instead of the unrelated `yfinance` package, and document `search`
- **Docs**: Removed `GEMINI.md`, which duplicated the README and had gone stale

## [0.3.0] - 2026-10-01

### Changed
- **Breaking (CLI)**: The `yfinance` CLI runs on [treaty](https://github.com/romamo/treaty) instead of `pydantic-settings`
  - Output is a JSON envelope (`ok`, `data`, `error`, `meta`) whenever stdout is not a terminal; `--format plain` prints text, `--format tsv` a table
  - Exit codes: `5` (`NOT_FOUND`) when nothing matches (was `3`); `2` for invalid arguments, now with every error listed in `error.errors`
  - `-v`/`-vv` become treaty's `--verbose`/`--debug`; `--schema` prints the command's input and output schema
  - `lookup --report-price` is gone: the price is always in the output
  - `lookup --asset-class` takes the lowercase `AssetClass` values (`equity`, not `Equity`), which `--schema` lists; `lookup --limit` is gone
  - Data from Yahoo is marked `_trusted: false`, and text formats warn `UNTRUSTED_CONTENT` on stderr
- **CLI**: New agent features from treaty: `--validate-only`, `--fields`, `--timeout`, `manifest`, and `completion`
- **Dependencies**: Added `treaty==1.0.0rc11`; bumped `pydantic-market-data` to `>=0.6.1`, whose typed `asset_class` and `date` give the schema their allowed values; dropped the direct `pydantic-settings` pin

### Removed
- `py_yfinance.logging_utils`: treaty configures logging

## [0.2.1] - 2026-10-01

### Changed
- **Dependencies**: Bumped `pydantic-market-data` to `>=0.5.0`, whose `History` rejects candles that are not in strictly ascending date order; `history` builds candles in Yahoo's row order, which was ascending for every symbol and period checked

## [0.2.0] - 2026-09-30

### Changed
- **Breaking**: Requires Python 3.14 or later
- **Breaking (CLI)**: Typed exit codes: `2` for invalid arguments, `3` when nothing is found (was `1`); errors go to stderr
- **CLI**: Flags that a command ignored (`lookup --desc/--country/--limit`, `history --desc/--exchange/--date/--price`) and unknown `--format` values now exit `2` instead of being silently dropped
- **CLI**: `lookup --price` and `--date` must be passed together; `--asset-class` is validated against `AssetClass`
- **CLI**: `search --format json` prints `[]` when nothing matches, so stdout is always valid JSON
- **Dependencies**: `pytest` moved from runtime to the `dev` dependency group

### Fixed
- **`resolve`**: Crashed with `AttributeError` whenever `price_on` was set, since `pydantic-market-data` 0.4.1 made it a list; a candidate must now match every price point
- **`resolve`**: `asset_class` filtering used string matching on the enum, so `FX`, `COMMODITY`, `FIXED_INCOME`, and `DERIVATIVE` never matched; it now maps each `AssetClass` to its Yahoo quote types
- **`resolve`**: `asset_class` now also filters ISIN candidates, not only symbol candidates
- **CLI**: `history --isin` passed the ISIN to Yahoo as a symbol; it now resolves the ISIN first
- **CLI**: `history` with no candles exits `3` instead of printing `Candles: 0`

## [0.1.17] - 2026-05-12

### Changed
- **`resolve`**: `asset_class` is now a proper `AssetClass` enum value (mapped from yfinance `quoteType`) instead of a raw string.
- **`resolve`**: Added `security_type` field to `SearchResult` (e.g. `"Equity"`, `"Etf"`).
- **Dependencies**: Bumped `pydantic-market-data` to `>=0.4.0`, pinned `pydantic-settings==2.14.1`.

## [0.1.16] - 2026-05-08

### Added
- **Validation**: `price_tolerance` parameter on `validate` (default `0.10`) and `_validate_candidate_data` — allows prices outside the daily OHLC range if within the given percentage of close.

### Changed
- **Dependencies**: Bumped `pydantic-market-data` to `>=0.3.2`.

## [0.1.15] - 2026-04-23

### Changed
- **Breaking**: Aligned with `pydantic-market-data>=0.3.0` — `SecurityCriteria` renamed to `SecurityQuery`; separate `target_price` / `target_date` fields replaced by a single `price_on: PriceOnDate | None` field.
- **Dependencies**: Bumped `yfinance>=1.3.0` and `pydantic-settings>=2.14.0`.

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

