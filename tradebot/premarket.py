from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import TradingSettings
from .models import LiveQuote


MARKET_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
SECTOR_SYMBOLS = ("SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "TSM")
TRADING_SYMBOLS = ("SOXL", "SOXS")
PREMARKET_QUOTE_SYMBOLS = TRADING_SYMBOLS + MARKET_SYMBOLS + SECTOR_SYMBOLS


@dataclass(frozen=True)
class PremarketAssessment:
    market_change_pct: float | None
    semiconductor_change_pct: float | None
    soxl_change_pct: float | None
    soxs_change_pct: float | None
    bias: str
    risk_mode: str
    monitor_cadence_minutes: int
    allowed_entry_symbols: tuple[str, ...]
    rationale: str


def average_change_pct(quotes: dict[str, LiveQuote], symbols: tuple[str, ...]) -> float | None:
    changes = [
        quote.daily_change_pct
        for symbol in symbols
        if (quote := quotes.get(symbol)) is not None and quote.daily_change_pct is not None
    ]
    if not changes:
        return None
    return sum(changes) / len(changes)


def assess_premarket(settings: TradingSettings, quotes: dict[str, LiveQuote]) -> PremarketAssessment:
    market_change = average_change_pct(quotes, MARKET_SYMBOLS)
    semiconductor_change = average_change_pct(quotes, SECTOR_SYMBOLS)
    soxl_change = _change(quotes, "SOXL")
    soxs_change = _change(quotes, "SOXS")

    if soxl_change is None or soxs_change is None:
        return PremarketAssessment(
            market_change_pct=market_change,
            semiconductor_change_pct=semiconductor_change,
            soxl_change_pct=soxl_change,
            soxs_change_pct=soxs_change,
            bias="insufficient-data",
            risk_mode="blocked",
            monitor_cadence_minutes=15,
            allowed_entry_symbols=(),
            rationale="SOXL and SOXS quotes are required before planning live entries.",
        )

    max_session_move = settings.daytrade_strategy.max_session_move_pct
    if abs(soxl_change) > max_session_move:
        return PremarketAssessment(
            market_change_pct=market_change,
            semiconductor_change_pct=semiconductor_change,
            soxl_change_pct=soxl_change,
            soxs_change_pct=soxs_change,
            bias="shock-down" if soxl_change < 0 else "shock-up",
            risk_mode="blocked",
            monitor_cadence_minutes=15,
            allowed_entry_symbols=(),
            rationale=(
                f"SOXL move {soxl_change:.2f}% exceeds configured max session move "
                f"{max_session_move:.2f}%."
            ),
        )

    market_is_positive = market_change is not None and market_change > 0
    market_is_negative = market_change is not None and market_change < 0
    semis_are_positive = semiconductor_change is not None and semiconductor_change > 0
    semis_are_negative = semiconductor_change is not None and semiconductor_change < 0

    if abs(soxl_change) >= 8.0:
        if soxl_change > 0 and (semis_are_positive or market_is_positive):
            return PremarketAssessment(
                market_change_pct=market_change,
                semiconductor_change_pct=semiconductor_change,
                soxl_change_pct=soxl_change,
                soxs_change_pct=soxs_change,
                bias="bullish-semiconductors",
                risk_mode="defensive",
                monitor_cadence_minutes=10,
                allowed_entry_symbols=("SOXL",),
                rationale="SOXL move is large and directionally confirmed; require stricter live confirmation.",
            )
        if soxl_change < 0 and (semis_are_negative or market_is_negative):
            return PremarketAssessment(
                market_change_pct=market_change,
                semiconductor_change_pct=semiconductor_change,
                soxl_change_pct=soxl_change,
                soxs_change_pct=soxs_change,
                bias="bearish-semiconductors",
                risk_mode="defensive",
                monitor_cadence_minutes=10,
                allowed_entry_symbols=("SOXS",),
                rationale="SOXL move is large and directionally confirmed; require stricter live confirmation.",
            )
        return PremarketAssessment(
            market_change_pct=market_change,
            semiconductor_change_pct=semiconductor_change,
            soxl_change_pct=soxl_change,
            soxs_change_pct=soxs_change,
            bias="high-volatility-mixed",
            risk_mode="defensive",
            monitor_cadence_minutes=10,
            allowed_entry_symbols=(),
            rationale="SOXL move is large but confirmation is mixed; wait for regular-hours confirmation.",
        )

    if soxl_change >= 2.0 and (semis_are_positive or market_is_positive):
        return PremarketAssessment(
            market_change_pct=market_change,
            semiconductor_change_pct=semiconductor_change,
            soxl_change_pct=soxl_change,
            soxs_change_pct=soxs_change,
            bias="bullish-semiconductors",
            risk_mode="normal",
            monitor_cadence_minutes=5,
            allowed_entry_symbols=("SOXL",),
            rationale="SOXL is up materially and market or semiconductor confirmation is positive.",
        )
    if soxl_change <= -2.0 and (semis_are_negative or market_is_negative):
        return PremarketAssessment(
            market_change_pct=market_change,
            semiconductor_change_pct=semiconductor_change,
            soxl_change_pct=soxl_change,
            soxs_change_pct=soxs_change,
            bias="bearish-semiconductors",
            risk_mode="normal",
            monitor_cadence_minutes=5,
            allowed_entry_symbols=("SOXS",),
            rationale="SOXL is down materially and market or semiconductor confirmation is negative.",
        )
    return PremarketAssessment(
        market_change_pct=market_change,
        semiconductor_change_pct=semiconductor_change,
        soxl_change_pct=soxl_change,
        soxs_change_pct=soxs_change,
        bias="mixed",
        risk_mode="watch",
        monitor_cadence_minutes=10,
        allowed_entry_symbols=("SOXL", "SOXS"),
        rationale="No strong confirmed premarket directional edge; require live rule confirmation.",
    )


def build_premarket_plan(
    settings: TradingSettings,
    quotes: dict[str, LiveQuote],
    plan_date: date | None = None,
) -> str:
    plan_date = plan_date or date.today()
    assessment = assess_premarket(settings, quotes)
    allowed = ", ".join(assessment.allowed_entry_symbols) if assessment.allowed_entry_symbols else "none"

    lines = [
        f"# Premarket SOXL/SOXS Plan - {plan_date.isoformat()}",
        "",
        "## Snapshot",
        "",
        "- Live execution: disabled inside this report",
        "- Purpose: establish market/sector context before the adaptive monitor runs",
        f"- Bias: {assessment.bias}",
        f"- Risk mode: {assessment.risk_mode}",
        f"- Planned monitor cadence: {assessment.monitor_cadence_minutes} minutes",
        f"- Allowed opening symbols from plan: {allowed}",
        f"- Rationale: {assessment.rationale}",
        "",
        "## Quote Basket",
        "",
    ]

    lines.extend(_quote_section("Trading ETFs", quotes, TRADING_SYMBOLS))
    lines.extend([""])
    lines.extend(_quote_section("Market ETFs", quotes, MARKET_SYMBOLS))
    lines.extend([""])
    lines.extend(_quote_section("Semiconductor Context", quotes, SECTOR_SYMBOLS))
    lines.extend(
        [
            "",
            "## Monitor Instructions",
            "",
            "- The monitor must still enforce standing authorization, account state, buying power, order state, daily notional, and monthly realized-loss caps.",
            "- Do not place orders outside regular hours.",
            "- Do not open a new SOXL/SOXS position when a SOXL/SOXS position or open SOXL/SOXS order already exists.",
            "- If risk mode is blocked, skip all new opening buys until a later plan or live risk check clears the block.",
            "- If risk mode is defensive, skip opening buys unless regular-hours quotes meet the defensive live momentum threshold and all broker/account/order/exit checks are fresh.",
            "- When daytrade_strategy.require_fresh_history_for_live_entries is false, stale daily CSV history must not block live entries that are confirmed by fresh Robinhood quotes and a current-date plan.",
            "- If allowed opening symbols lists only one ETF, block opposite-direction opening buys for this session unless a later premarket or manual review updates the plan.",
            "- If a SOXL/SOXS position is open, use 5-minute cadence for exit monitoring regardless of the premarket cadence.",
        ]
    )
    return "\n".join(lines) + "\n"


def _change(quotes: dict[str, LiveQuote], symbol: str) -> float | None:
    quote = quotes.get(symbol)
    return None if quote is None else quote.daily_change_pct


def _quote_section(title: str, quotes: dict[str, LiveQuote], symbols: tuple[str, ...]) -> list[str]:
    lines = [f"### {title}", ""]
    for symbol in symbols:
        quote = quotes.get(symbol)
        if quote is None:
            lines.append(f"- {symbol}: missing")
            continue
        change = quote.daily_change_pct
        change_text = "n/a" if change is None else f"{change:.2f}%"
        lines.append(
            f"- {symbol}: ${quote.price:,.2f} ({change_text} vs previous close, "
            f"as of {quote.as_of.isoformat()}, state={quote.state})"
        )
    return lines
