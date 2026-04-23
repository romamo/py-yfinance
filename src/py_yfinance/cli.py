import logging
import sys

from pydantic import Field
from pydantic_market_data.cli_models import (
    GlobalArgs,
    HistoryArgs,
    PatchedCliSettingsSource,
    SearchArgs,
)
from pydantic_market_data.models import (
    Currency,
    Price,
    PriceOnDate,
    PriceVerificationError,
    Security,
    SecurityQuery,
    StrictDate,
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


class LookupCommand(SearchArgs):
    """Lookup a security by Symbol or ISIN"""

    report_price: bool = Field(False, description="Fetch and include current price in output")

    def cli_cmd(self) -> None:
        from pydantic import TypeAdapter

        if not (self.isin or self.symbol):
            logger.error("Error: At least one of --isin or --symbol must be provided.")
            sys.exit(1)

        target_price_vo = Price(self.price) if self.price else None
        target_date_vo = TypeAdapter(StrictDate).validate_python(self.date) if self.date else None

        price_on = None
        if target_price_vo is not None and target_date_vo is not None:
            price_on = PriceOnDate(price=target_price_vo, date=target_date_vo.value)

        criteria = SecurityQuery(
            isin=self.isin,
            symbol=self.symbol,
            price_on=price_on,
            exchange=self.exchange,
            currency=Currency(self.currency.upper()) if self.currency else None,
            asset_class=self.asset_class,
        )

        try:
            result = source.resolve(criteria)
        except PriceVerificationError as e:
            logger.error(f"Verification Failed: {e}")
            sys.exit(1)

        if result:
            if self.format == "json":
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
        else:
            print("Not found.")
            sys.exit(1)


class SearchCommand(BaseSettings):
    """Search for securities by query string"""

    query: str = Field(..., description="Search query string")
    format: str = Field("text", description="Output format (text, json)")

    def cli_cmd(self) -> None:
        results = source.search(self.query)

        if not results:
            print("No results found.")
            return

        if self.format == "json":
            from pydantic import TypeAdapter

            adapter = TypeAdapter(list[Security])
            print(adapter.dump_json(results, indent=2).decode())
        else:
            for res in results:
                symbol_str = (
                    str(res.symbol.root) if hasattr(res.symbol, "root") else str(res.symbol)
                )
                print(
                    f"{symbol_str:10} | {res.name[:40]:40} | "
                    f"{res.exchange or 'N/A':6} | {res.country or 'N/A'}"
                )


class HistoryCommand(HistoryArgs):
    """Get historical data for a symbol"""

    def cli_cmd(self) -> None:
        identifier = self.symbol or self.isin
        if not identifier:
            logger.error("Error: At least one of --symbol or --isin must be provided.")
            sys.exit(1)

        hist = source.history(Symbol(identifier), period=self.period)

        if self.format == "json":
            print(hist.model_dump_json(indent=2))
        else:
            print(f"Symbol: {hist.security.symbol}")
            print(f"Candles: {len(hist.candles)}")

            if hist.candles:
                last = hist.candles[-1]
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
