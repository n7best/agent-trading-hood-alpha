from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import LiveQuote


def parse_robinhood_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    text = re.sub(r"(\.\d{6})\d+([+-]\d{2}:\d{2})$", r"\1\2", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Unsupported Robinhood timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "0", "0.000000"):
        return None
    return float(value)


def _required_float(value: Any, label: str) -> float:
    if value in (None, ""):
        raise ValueError(f"Missing required quote value: {label}")
    return float(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


class RobinhoodMCPMarketData:
    """Parses `mcp__robinhood_trading.get_equity_quotes` responses."""

    source = "robinhood_mcp"

    @classmethod
    def load_snapshot(cls, path: str | Path) -> dict[str, LiveQuote]:
        snapshot_path = Path(path)
        with snapshot_path.open() as handle:
            payload = json.load(handle)
        return cls.parse_quotes(payload)

    @classmethod
    def parse_quotes(cls, payload: dict[str, Any]) -> dict[str, LiveQuote]:
        data = payload.get("data", payload)
        results = data.get("results")
        if not isinstance(results, list):
            raise ValueError("Robinhood MCP quote payload must contain data.results[]")

        quotes: dict[str, LiveQuote] = {}
        for result in results:
            quote = result.get("quote") if isinstance(result, dict) else None
            if not isinstance(quote, dict):
                continue
            live_quote = cls._parse_quote_result(quote, result.get("close"))
            quotes[live_quote.symbol] = live_quote
        if not quotes:
            raise ValueError("Robinhood MCP quote payload did not contain usable quotes")
        return quotes

    @classmethod
    def _parse_quote_result(cls, quote: dict[str, Any], close: dict[str, Any] | None) -> LiveQuote:
        symbol = str(quote["symbol"]).upper()

        regular_time = parse_robinhood_time(quote.get("venue_last_trade_time"))
        non_regular_time = parse_robinhood_time(quote.get("venue_last_non_reg_trade_time"))
        regular_price = _optional_float(quote.get("last_trade_price"))
        non_regular_price = _optional_float(quote.get("last_non_reg_trade_price"))

        if non_regular_price is not None and non_regular_time is not None:
            if regular_time is None or non_regular_time > regular_time:
                price = non_regular_price
                as_of = non_regular_time
            else:
                price = _required_float(regular_price, "last_trade_price")
                as_of = regular_time
        else:
            price = _required_float(regular_price, "last_trade_price")
            if regular_time is None:
                raise ValueError(f"Missing last trade timestamp for {symbol}")
            as_of = regular_time

        previous_close = _optional_float(quote.get("adjusted_previous_close"))
        if previous_close is None:
            previous_close = _optional_float(quote.get("previous_close"))
        if previous_close is None and isinstance(close, dict):
            previous_close = _optional_float(close.get("price"))

        return LiveQuote(
            symbol=symbol,
            price=price,
            as_of=as_of,
            source=cls.source,
            bid=_optional_float(quote.get("bid_price")),
            ask=_optional_float(quote.get("ask_price")),
            previous_close=previous_close,
            state=str(quote.get("state") or "unknown"),
            has_traded=_bool(quote.get("has_traded")),
        )


def write_quote_snapshot(path: str | Path, payload: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output
