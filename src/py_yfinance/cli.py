import datetime
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError
from pydantic_market_data.cli_models import CLASS, DATE, HistoryQueryArgs, SecurityQueryArgs
from pydantic_market_data.models import (
    AssetClass,
    Currency,
    History,
    PriceOnDate,
    Security,
    SecurityQuery,
    Symbol,
)
from treaty import App, Ctx, Exit, Format, RequiresAny

from py_yfinance.source import SearchResult, YFinanceDataSource

source = YFinanceDataSource()

app = App(
    "yfinance",
    version=version("py-yfinance"),
    description="Look up, search, and fetch history for securities on Yahoo Finance",
)


def _args_schema(cls: type[BaseModel]) -> dict[str, Any]:
    return cls.model_json_schema(by_alias=False)


def _args_validate(cls: type[BaseModel], data: dict[str, object]) -> BaseModel:
    return cls.model_validate(data, by_name=True, by_alias=False)


app.args_adapter(BaseModel, schema=_args_schema, validate=_args_validate)


def _output_schema(cls: type[BaseModel]) -> dict[str, Any]:
    return cls.model_json_schema(mode="serialization")


def _output_dump(obj: BaseModel) -> object:
    return obj.model_dump(mode="json", by_alias=True)


app.output_adapter(BaseModel, schema=_output_schema, dump=_output_dump)


def _reject_unsupported(command: str, **flags: object) -> None:
    passed = [f"--{name.replace('_', '-')}" for name, value in flags.items() if value]
    if passed:
        raise PydanticCustomError(
            "unsupported_flag", f"{command} does not support {', '.join(passed)}"
        )


class LookupArgs(SecurityQueryArgs):
    asset_class: CLASS | None = Field(
        None, description=f"Asset class: {', '.join(a.value for a in AssetClass)}"
    )
    date: DATE | None = Field(None, description="Date the security traded at --price (YYYY-MM-DD)")

    def asset_class_value(self) -> AssetClass | None:
        if self.asset_class is None:
            return None
        try:
            return AssetClass(self.asset_class.lower())
        except ValueError:
            choices = ", ".join(a.value for a in AssetClass)
            raise PydanticCustomError(
                "asset_class", f"--asset-class must be one of {choices}"
            ) from None

    def date_value(self) -> datetime.date | None:
        if self.date is None:
            return None
        try:
            return datetime.date.fromisoformat(self.date)
        except ValueError:
            raise PydanticCustomError("date", "--date must be a date as YYYY-MM-DD") from None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _reject_unsupported("lookup", desc=self.desc, country=self.country, limit=self.limit != 1)
        if (self.price is None) != (self.date is None):
            raise PydanticCustomError(
                "flags_together", "--price and --date must be provided together"
            )
        self.asset_class_value()
        self.date_value()
        return self


@app.command(
    "lookup",
    description="Resolve a security by symbol or ISIN, verified against recent prices",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    has_network_io=True,
    external=True,
    requires=[RequiresAny(("isin", "symbol"))],
    examples=[
        ("Look up Apple by symbol", "yfinance lookup --symbol AAPL"),
        ("Look up Apple by ISIN", "yfinance lookup --isin US0378331005"),
        (
            "Check that a symbol traded at a price on a date",
            "yfinance lookup --symbol AAPL --price 185 --date 2024-01-02",
        ),
    ],
)
def lookup(args: LookupArgs, ctx: Ctx) -> SearchResult:
    price_on = None
    target_date = args.date_value()
    if args.price is not None and target_date is not None:
        price_on = [PriceOnDate(price=args.price, date=target_date)]

    criteria = SecurityQuery(
        isin=args.isin,
        symbol=args.symbol,
        price_on=price_on,
        exchange=args.exchange,
        currency=Currency(args.currency) if args.currency else None,
        asset_class=args.asset_class_value(),
    )
    result = source.resolve(criteria)
    if result is None:
        raise Exit.NOT_FOUND(
            "no security matches the given criteria",
            context={"symbol": args.symbol, "isin": args.isin},
        )
    return result


class HistoryArgs(HistoryQueryArgs):
    @model_validator(mode="after")
    def _check(self) -> Self:
        _reject_unsupported(
            "history", desc=self.desc, exchange=self.exchange, date=self.date, price=self.price
        )
        return self


def _number(value: float | None, decimals: int = 2) -> str:
    return "" if value is None else f"{value:,.{decimals}f}"


def render_history(data: Mapping[str, Any]) -> str:
    lines = [f"Symbol: {data['security']['symbol']}"]
    lines.append(
        f"{'date':10}  {'open':>12}  {'high':>12}  {'low':>12}  {'close':>12}  {'volume':>16}"
    )
    for c in data["candles"]:
        lines.append(
            f"{c['date'][:10]:10}  {_number(c['open']):>12}  {_number(c['high']):>12}  "
            f"{_number(c['low']):>12}  {_number(c['close']):>12}  {_number(c['volume'], 0):>16}"
        )
    return "\n".join(lines) + "\n"


@app.command(
    "history",
    description="Fetch daily candles for a symbol, or for the security an ISIN resolves to",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    has_network_io=True,
    external=True,
    requires=[RequiresAny(("isin", "symbol"))],
    renderers={Format.PLAIN: render_history},
    examples=[
        ("Last month of Apple candles", "yfinance history --symbol AAPL"),
        ("Five days of candles by ISIN", "yfinance history --isin US0378331005 --period 5d"),
    ],
)
def history(args: HistoryArgs, ctx: Ctx) -> History:
    if args.symbol:
        symbol = Symbol(args.symbol)
    else:
        resolved = source.resolve(SecurityQuery(isin=args.isin))
        if resolved is None:
            raise Exit.NOT_FOUND("no security matches the ISIN", context={"isin": args.isin})
        symbol = resolved.symbol if isinstance(resolved.symbol, Symbol) else Symbol(resolved.symbol)

    hist = source.history(symbol, period=args.period)
    if not hist.candles:
        raise Exit.NOT_FOUND(
            "no history for the symbol",
            context={"symbol": symbol.root, "period": args.period.value},
        )
    return hist


class SearchArgs(BaseModel):
    query: str = Field(
        description="Text to search for: a name, symbol, or ISIN",
        json_schema_extra={"treaty": {"positional": True}},
    )


def render_search(data: Sequence[Mapping[str, Any]]) -> str:
    return "".join(
        f"{r['symbol']:10} | {(r['name'] or '')[:40]:40} | "
        f"{r['exchange'] or 'N/A':6} | {r['country'] or 'N/A'}\n"
        for r in data
    )


@app.command(
    "search",
    description="Search securities by free text, in Yahoo's relevance order",
    danger_level="safe",
    exit_codes=[],
    has_network_io=True,
    external=True,
    ordered=True,
    renderers={Format.PLAIN: render_search},
    examples=[("Find securities named Tesla", "yfinance search tesla")],
)
def search(args: SearchArgs, ctx: Ctx) -> list[Security]:
    return source.search(args.query)


def main() -> None:
    app.main()


if __name__ == "__main__":
    main()
