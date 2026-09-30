import logging
import sys
from enum import IntEnum, StrEnum
from typing import NoReturn

from pydantic import Field, TypeAdapter, ValidationError
from pydantic_market_data.cli_models import (
    GlobalArgs,
    HistoryArgs,
    PatchedCliSettingsSource,
    SearchArgs,
)
from pydantic_market_data.models import (
    AssetClass,
    Currency,
    PriceOnDate,
    Security,
    SecurityQuery,
    Symbol,
)
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSubCommand,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from py_yfinance.logging_utils import setup_logging
from py_yfinance.source import YFinanceDataSource

source = YFinanceDataSource()
logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    """Process exit codes; USAGE matches argparse's own exit code for bad arguments"""

    OK = 0
    ERROR = 1
    USAGE = 2
    NOT_FOUND = 3


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


def _fail(code: ExitCode, message: str) -> NoReturn:
    logger.error(message)
    sys.exit(code)


def _output_format(value: str) -> OutputFormat:
    try:
        return OutputFormat(value)
    except ValueError:
        choices = ", ".join(f.value for f in OutputFormat)
        _fail(ExitCode.USAGE, f"Invalid --format {value!r}: expected one of {choices}")


def _reject_unsupported(command: str, **flags: object) -> None:
    passed = [f"--{name.replace('_', '-')}" for name, value in flags.items() if value]
    if passed:
        _fail(ExitCode.USAGE, f"{command} does not support {', '.join(passed)}")


class LookupCommand(SearchArgs):
    """Lookup a security by Symbol or ISIN"""

    report_price: bool = Field(False, description="Fetch and include current price in output")

    def cli_cmd(self) -> None:
        output_format = _output_format(self.format)
        _reject_unsupported("lookup", desc=self.desc, country=self.country, limit=self.limit != 1)

        if not (self.isin or self.symbol):
            _fail(ExitCode.USAGE, "At least one of --isin or --symbol must be provided")

        if (self.price is None) != (self.date is None):
            _fail(ExitCode.USAGE, "--price and --date must be provided together")

        price_on: list[PriceOnDate] = []
        if self.price is not None and self.date is not None:
            try:
                price_on = [PriceOnDate.model_validate({"price": self.price, "date": self.date})]
            except ValidationError as e:
                _fail(ExitCode.USAGE, f"Invalid --price/--date: {e}")

        asset_class = None
        if self.asset_class:
            try:
                asset_class = AssetClass(self.asset_class.lower())
            except ValueError:
                choices = ", ".join(a.value for a in AssetClass)
                _fail(
                    ExitCode.USAGE,
                    f"Invalid --asset-class {self.asset_class!r}: expected one of {choices}",
                )

        criteria = SecurityQuery(
            isin=self.isin,
            symbol=self.symbol,
            price_on=price_on or None,
            exchange=self.exchange,
            currency=Currency(self.currency.upper()) if self.currency else None,
            asset_class=asset_class,
        )

        result = source.resolve(criteria)
        if result is None:
            _fail(ExitCode.NOT_FOUND, "No security matches the given criteria")

        if output_format is OutputFormat.JSON:
            # Price is already populated in result if resolve succeeded
            print(result.model_dump_json(indent=2))
        else:
            price_str = ""
            if self.report_price and result.price:
                label = f"Price on {self.date}" if self.date else "Last Price"
                price_str = f" [{label}: {result.price.root:.2f} {result.currency}]"

            print(f"Symbol: {result.symbol}")
            print(f"Name: {result.name}")
            print(f"Exchange: {result.exchange}")
            print(f"Currency: {result.currency}{price_str}")


class SearchCommand(BaseSettings):
    """Search for securities by query string"""

    query: str = Field(..., description="Search query string")
    format: str = Field("text", description="Output format (text, json)")

    def cli_cmd(self) -> None:
        output_format = _output_format(self.format)
        results = source.search(self.query)

        if output_format is OutputFormat.JSON:
            adapter = TypeAdapter(list[Security])
            print(adapter.dump_json(results, indent=2).decode())
            return

        if not results:
            logger.warning("No results found.")
            return

        for res in results:
            symbol_str = str(res.symbol.root) if hasattr(res.symbol, "root") else str(res.symbol)
            print(
                f"{symbol_str:10} | {res.name[:40]:40} | "
                f"{res.exchange or 'N/A':6} | {res.country or 'N/A'}"
            )


class HistoryCommand(HistoryArgs):
    """Get historical data for a symbol"""

    def cli_cmd(self) -> None:
        output_format = _output_format(self.format)
        _reject_unsupported(
            "history", desc=self.desc, exchange=self.exchange, date=self.date, price=self.price
        )

        if self.symbol:
            symbol = Symbol(self.symbol)
        elif self.isin:
            resolved = source.resolve(SecurityQuery(isin=self.isin))
            if resolved is None:
                _fail(ExitCode.NOT_FOUND, f"No security matches ISIN {self.isin}")
            symbol = (
                resolved.symbol if isinstance(resolved.symbol, Symbol) else Symbol(resolved.symbol)
            )
        else:
            _fail(ExitCode.USAGE, "At least one of --symbol or --isin must be provided")

        hist = source.history(symbol, period=self.period)
        if not hist.candles:
            _fail(ExitCode.NOT_FOUND, f"No history for {symbol.root} over {self.period.value}")

        if output_format is OutputFormat.JSON:
            print(hist.model_dump_json(indent=2))
        else:
            last = hist.candles[-1]
            print(f"Symbol: {hist.security.symbol}")
            print(f"Candles: {len(hist.candles)}")
            print(f"Last Candle ({last.date}): Close=${last.close}")


class AppCLI(BaseSettings, GlobalArgs):
    """yfinance CLI Application"""

    model_config = SettingsConfigDict(
        cli_parse_args=True,
        cli_kebab_case=True,
        cli_implicit_flags="toggle",
        cli_hide_none_type=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            PatchedCliSettingsSource(settings_cls),
        )

    lookup: CliSubCommand[LookupCommand]
    history: CliSubCommand[HistoryCommand]
    search: CliSubCommand[SearchCommand]

    def cli_cmd(self) -> None:
        # Resolve the active subcommand (the one that is not None)
        subcommand = (
            self.lookup
            if self.lookup is not None
            else self.history
            if self.history is not None
            else self.search
        )
        # Propagate v/vv flags from subcommand
        v = self.v or getattr(subcommand, "v", False)
        vv = self.vv or getattr(subcommand, "vv", False)
        setup_logging(v, vv)
        CliApp.run_subcommand(self)


def main():
    CliApp.run(AppCLI)


if __name__ == "__main__":
    main()
