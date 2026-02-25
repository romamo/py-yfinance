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
    PriceVerificationError,
    SecurityCriteria,
    StrictDate,
    Ticker,
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
        target_price_vo = Price(self.price) if self.price else None
        target_date_vo = TypeAdapter(StrictDate).validate_python(self.date) if self.date else None

        criteria = SecurityCriteria(
            isin=self.isin,
            symbol=self.ticker,
            target_price=target_price_vo,
            target_date=target_date_vo.value if target_date_vo else None,
            exchange=self.exchange,
            currency=Currency(self.currency.upper()) if self.currency else None,
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

                print(f"Ticker: {result.ticker}")
                print(f"Name: {result.name}")
                print(f"Exchange: {result.exchange}")
                print(f"Currency: {result.currency}{price_str}")
        else:
            print("Not found.")
            sys.exit(1)


class HistoryCommand(HistoryArgs):
    """Get historical data for a ticker"""

    def cli_cmd(self) -> None:
        hist = source.history(Ticker(self.ticker or self.isin or ""), period=self.period)

        if self.format == "json":
            print(hist.model_dump_json(indent=2))
        else:
            print(f"Symbol: {hist.symbol.ticker}")
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

    def cli_cmd(self) -> None:
        # Resolve the active subcommand (the one that is not None)
        subcommand = self.lookup if self.lookup is not None else self.history
        # Propagate v/vv flags from subcommand
        v = self.v or getattr(subcommand, "v", False)
        vv = self.vv or getattr(subcommand, "vv", False)
        setup_logging(v, vv)
        CliApp.run_subcommand(self)


def main():
    CliApp.run(AppCLI)


if __name__ == "__main__":
    main()
