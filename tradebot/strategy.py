from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .indicators import simple_moving_average
from .models import Bar, LiveQuote, PairSignal, TradeSignal


@dataclass(frozen=True)
class MovingAverageCrossoverStrategy:
    fast_window: int = 10
    slow_window: int = 30
    name: str = "moving_average_crossover"

    def __post_init__(self) -> None:
        if self.fast_window <= 0 or self.slow_window <= 0:
            raise ValueError("strategy windows must be positive")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be lower than slow_window")

    def generate_signals(self, bars: list[Bar]) -> list[TradeSignal]:
        closes = [bar.close for bar in bars]
        fast = simple_moving_average(closes, self.fast_window)
        slow = simple_moving_average(closes, self.slow_window)
        signals: list[TradeSignal] = []

        for index in range(1, len(bars)):
            previous_fast = fast[index - 1]
            previous_slow = slow[index - 1]
            current_fast = fast[index]
            current_slow = slow[index]
            if None in (previous_fast, previous_slow, current_fast, current_slow):
                continue

            bar = bars[index]
            if previous_fast <= previous_slow and current_fast > current_slow:
                signals.append(
                    TradeSignal(
                        timestamp=bar.timestamp,
                        symbol=bar.symbol,
                        side="buy",
                        price=bar.close,
                        reason=f"SMA {self.fast_window} crossed above SMA {self.slow_window}",
                    )
                )
            elif previous_fast >= previous_slow and current_fast < current_slow:
                signals.append(
                    TradeSignal(
                        timestamp=bar.timestamp,
                        symbol=bar.symbol,
                        side="sell",
                        price=bar.close,
                        reason=f"SMA {self.fast_window} crossed below SMA {self.slow_window}",
                    )
                )

        return signals


@dataclass(frozen=True)
class SoxlSoxsRulesStrategy:
    fast_window: int = 5
    slow_window: int = 20
    min_confirmation_return_pct: float = 0.5
    max_chase_return_pct: float = 8.0
    name: str = "soxl_soxs_rules"

    def __post_init__(self) -> None:
        if self.fast_window <= 0 or self.slow_window <= 0:
            raise ValueError("strategy windows must be positive")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be lower than slow_window")
        if self.min_confirmation_return_pct < 0:
            raise ValueError("min_confirmation_return_pct cannot be negative")
        if self.max_chase_return_pct <= 0:
            raise ValueError("max_chase_return_pct must be positive")

    def generate_pair_signals(self, bars_by_symbol: dict[str, list[Bar]]) -> list[PairSignal]:
        soxl_bars = bars_by_symbol.get("SOXL", [])
        soxs_by_date = {bar.timestamp.date(): bar for bar in bars_by_symbol.get("SOXS", [])}
        if not soxl_bars or not soxs_by_date:
            raise ValueError("SOXL and SOXS bars are required")

        closes = [bar.close for bar in soxl_bars]
        fast = simple_moving_average(closes, self.fast_window)
        slow = simple_moving_average(closes, self.slow_window)
        signals: list[PairSignal] = []

        for index in range(1, len(soxl_bars)):
            soxl_bar = soxl_bars[index]
            soxs_bar = soxs_by_date.get(soxl_bar.timestamp.date())
            if soxs_bar is None:
                continue
            if fast[index] is None or slow[index] is None:
                continue

            previous_close = soxl_bars[index - 1].close
            if previous_close <= 0:
                continue
            soxl_return_pct = ((soxl_bar.close / previous_close) - 1) * 100
            target_symbol: str | None = None
            target_price: float | None = None
            reason = "no trade: trend or confirmation filter failed"

            if abs(soxl_return_pct) > self.max_chase_return_pct:
                reason = (
                    "no trade: SOXL daily move "
                    f"{soxl_return_pct:.2f}% exceeds max chase {self.max_chase_return_pct:.2f}%"
                )
            elif fast[index] > slow[index] and soxl_return_pct >= self.min_confirmation_return_pct:
                target_symbol = "SOXL"
                target_price = soxl_bar.close
                reason = (
                    f"bullish: SOXL SMA {self.fast_window}>{self.slow_window} "
                    f"and return {soxl_return_pct:.2f}%"
                )
            elif fast[index] < slow[index] and soxl_return_pct <= -self.min_confirmation_return_pct:
                target_symbol = "SOXS"
                target_price = soxs_bar.close
                reason = (
                    f"bearish: SOXL SMA {self.fast_window}<{self.slow_window} "
                    f"and return {soxl_return_pct:.2f}%"
                )

            signals.append(
                PairSignal(
                    timestamp=soxl_bar.timestamp,
                    target_symbol=target_symbol,
                    price=target_price,
                    reason=reason,
                )
            )

        return signals


@dataclass(frozen=True)
class AggressiveSoxlSoxsDayTradeStrategy:
    lookback_window: int = 3
    trend_window: int = 8
    min_session_move_pct: float = 0.25
    min_prior_return_pct: float = 1.0
    max_session_move_pct: float = 18.0
    name: str = "aggressive_soxl_soxs_daytrade"

    def __post_init__(self) -> None:
        if self.lookback_window <= 0 or self.trend_window <= 1:
            raise ValueError("lookback_window and trend_window must be positive")
        if self.min_session_move_pct < 0 or self.min_prior_return_pct < 0:
            raise ValueError("confirmation thresholds cannot be negative")
        if self.max_session_move_pct <= 0:
            raise ValueError("max_session_move_pct must be positive")

    def generate_pair_signals(self, bars_by_symbol: dict[str, list[Bar]]) -> list[PairSignal]:
        soxl_bars = bars_by_symbol.get("SOXL", [])
        soxs_by_date = {bar.timestamp.date(): bar for bar in bars_by_symbol.get("SOXS", [])}
        if not soxl_bars or not soxs_by_date:
            raise ValueError("SOXL and SOXS bars are required")

        closes = [bar.close for bar in soxl_bars]
        trend = simple_moving_average(closes, self.trend_window)
        signals: list[PairSignal] = []

        start_index = max(self.lookback_window, self.trend_window)
        for index in range(start_index, len(soxl_bars)):
            current = soxl_bars[index]
            previous = soxl_bars[index - 1]
            lookback = soxl_bars[index - self.lookback_window]
            if current.timestamp.date() not in soxs_by_date:
                continue
            if previous.close <= 0 or lookback.close <= 0 or trend[index - 1] is None:
                continue

            session_move_pct = ((current.close / previous.close) - 1) * 100
            prior_return_pct = ((previous.close / lookback.close) - 1) * 100
            target_symbol: str | None = None
            target_price: float | None = None
            reason = "no trade: aggressive day-trade filters not met"

            if abs(session_move_pct) > self.max_session_move_pct:
                reason = (
                    "no trade: SOXL session move "
                    f"{session_move_pct:.2f}% exceeds max {self.max_session_move_pct:.2f}%"
                )
            elif (
                previous.close > trend[index - 1]
                and (
                    session_move_pct >= self.min_session_move_pct
                    or prior_return_pct >= self.min_prior_return_pct
                )
            ):
                target_symbol = "SOXL"
                target_price = current.close
                reason = (
                    f"aggressive long SOXL: prior close above SMA {self.trend_window}, "
                    f"session move {session_move_pct:.2f}%, "
                    f"prior {self.lookback_window}-bar return {prior_return_pct:.2f}%"
                )
            elif (
                previous.close < trend[index - 1]
                and (
                    session_move_pct <= -self.min_session_move_pct
                    or prior_return_pct <= -self.min_prior_return_pct
                )
            ):
                target_symbol = "SOXS"
                target_price = soxs_by_date[current.timestamp.date()].close
                reason = (
                    f"aggressive long SOXS: prior close below SMA {self.trend_window}, "
                    f"SOXL session move {session_move_pct:.2f}%, "
                    f"prior {self.lookback_window}-bar return {prior_return_pct:.2f}%"
                )

            signals.append(
                PairSignal(
                    timestamp=current.timestamp,
                    target_symbol=target_symbol,
                    price=target_price,
                    reason=reason,
                )
            )

        return signals


def generate_live_momentum_signal(
    soxl_quote: LiveQuote,
    soxs_quote: LiveQuote,
    *,
    allowed_symbols: Sequence[str],
    risk_mode: str,
    min_session_move_pct: float,
    max_session_move_pct: float,
    defensive_min_session_move_pct: float = 2.0,
    allow_stale_plan_live_fallback: bool = False,
    stale_plan_min_session_move_pct: float = 4.0,
) -> PairSignal:
    """Live-only SOXL/SOXS entry signal from fresh broker quotes and session plan.

    Daily CSV history is intentionally not part of this decision. Those files are
    backtest inputs; live entries depend on the broker's current quote, official
    prior close, and the current-date premarket plan's allowed direction.
    """

    allowed = {symbol.upper() for symbol in allowed_symbols}
    mode = risk_mode.strip().lower()
    timestamp = max(soxl_quote.as_of, soxs_quote.as_of)

    if mode == "blocked" or (mode == "stale" and not allow_stale_plan_live_fallback):
        return PairSignal(
            timestamp=timestamp,
            target_symbol=None,
            price=None,
            reason=f"no trade: premarket risk mode {mode} blocks live entries",
        )
    if soxl_quote.state != "active" or soxs_quote.state != "active":
        return PairSignal(
            timestamp=timestamp,
            target_symbol=None,
            price=None,
            reason="no trade: SOXL/SOXS quotes must both be active",
        )
    if not soxl_quote.has_traded or not soxs_quote.has_traded:
        return PairSignal(
            timestamp=timestamp,
            target_symbol=None,
            price=None,
            reason="no trade: SOXL/SOXS quotes must both have regular-session trades",
        )

    session_move_pct = soxl_quote.daily_change_pct
    if session_move_pct is None:
        return PairSignal(
            timestamp=timestamp,
            target_symbol=None,
            price=None,
            reason="no trade: SOXL official prior close is unavailable",
        )
    if abs(session_move_pct) > max_session_move_pct:
        return PairSignal(
            timestamp=timestamp,
            target_symbol=None,
            price=None,
            reason=(
                "no trade: SOXL session move "
                f"{session_move_pct:.2f}% exceeds max {max_session_move_pct:.2f}%"
            ),
        )

    stale_fallback = mode == "stale" and allow_stale_plan_live_fallback
    if stale_fallback:
        threshold = stale_plan_min_session_move_pct
        allowed = {"SOXL", "SOXS"}
    else:
        threshold = defensive_min_session_move_pct if mode == "defensive" else min_session_move_pct

    if session_move_pct >= threshold:
        if "SOXL" not in allowed:
            return PairSignal(
                timestamp=timestamp,
                target_symbol=None,
                price=None,
                reason="no trade: live momentum is bullish but plan does not allow SOXL",
            )
        return PairSignal(
            timestamp=timestamp,
            target_symbol="SOXL",
            price=soxl_quote.price,
            reason=(
                (
                    "live momentum fallback long SOXL: stale premarket plan, "
                    if stale_fallback
                    else "live momentum long SOXL: current-date plan allows SOXL, "
                )
                + f"risk mode {mode}, SOXL session move {session_move_pct:.2f}%"
            ),
        )

    if session_move_pct <= -threshold:
        if "SOXS" not in allowed:
            return PairSignal(
                timestamp=timestamp,
                target_symbol=None,
                price=None,
                reason="no trade: live momentum is bearish but plan does not allow SOXS",
            )
        return PairSignal(
            timestamp=timestamp,
            target_symbol="SOXS",
            price=soxs_quote.price,
            reason=(
                (
                    "live momentum fallback long SOXS: stale premarket plan, "
                    if stale_fallback
                    else "live momentum long SOXS: current-date plan allows SOXS, "
                )
                + f"risk mode {mode}, SOXL session move {session_move_pct:.2f}%"
            ),
        )

    return PairSignal(
        timestamp=timestamp,
        target_symbol=None,
        price=None,
        reason=(
            "no trade: SOXL session move "
            f"{session_move_pct:.2f}% has not reached live momentum threshold {threshold:.2f}%"
        ),
    )
