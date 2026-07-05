from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .authorization import AuthorizationPolicy, parse_policy_date
from .risk import RiskPolicy


@dataclass(frozen=True)
class PairStrategySettings:
    name: str
    fast_window: int
    slow_window: int
    min_confirmation_return_pct: float
    max_chase_return_pct: float
    order_amount: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_notional: float
    max_monthly_realized_loss: float


@dataclass(frozen=True)
class DayTradeStrategySettings:
    name: str
    lookback_window: int
    trend_window: int
    min_session_move_pct: float
    min_prior_return_pct: float
    max_session_move_pct: float
    live_entry_source: str
    require_fresh_history_for_live_entries: bool
    allow_stale_plan_live_fallback: bool
    stale_plan_min_session_move_pct: float
    defensive_min_session_move_pct: float
    order_amount: float
    stop_loss_pct: float
    take_profit_pct: float
    runner_enabled: bool
    initial_take_profit_pct: float
    initial_exit_fraction: float
    runner_stop_loss_pct: float
    runner_take_profit_pct: float
    runner_trailing_stop_pct: float
    max_daily_notional: float
    max_monthly_realized_loss: float


@dataclass(frozen=True)
class TradingSettings:
    config_path: Path
    initial_cash: float
    monthly_profit_target: float
    mode: str
    symbols: list[str]
    data_source: str
    csv_path: Path
    quote_snapshot_path: Path
    journal_path: Path
    strategy_name: str
    fast_window: int
    slow_window: int
    pair_strategy: PairStrategySettings
    daytrade_strategy: DayTradeStrategySettings
    risk: RiskPolicy
    authorization: AuthorizationPolicy


def _repo_relative(base_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_path / path).resolve()


def load_settings(config_path: str | Path = "config/trading.toml") -> TradingSettings:
    path = Path(config_path).resolve()
    with path.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)

    base_path = path.parent.parent if path.parent.name == "config" else path.parent
    account = raw.get("account", {})
    risk = raw.get("risk", {})
    strategy = raw.get("strategy", {})
    pair_strategy = raw.get("pair_strategy", {})
    daytrade_strategy = raw.get("daytrade_strategy", {})
    data = raw.get("data", {})
    journal = raw.get("journal", {})
    authorization = raw.get("authorization", {})

    mode = os.getenv("TRADING_MODE", str(account.get("mode", "paper"))).lower()
    symbols = [str(symbol).upper() for symbol in data.get("symbols", ["SPY"])]

    policy = RiskPolicy(
        initial_cash=float(account.get("initial_cash", 500.0)),
        monthly_profit_target=float(account.get("monthly_profit_target", 100.0)),
        max_risk_per_trade_pct=float(risk.get("max_risk_per_trade_pct", 0.01)),
        max_position_value_pct=float(risk.get("max_position_value_pct", 0.25)),
        max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 0.03)),
        max_monthly_loss_pct=float(risk.get("max_monthly_loss_pct", 0.08)),
        stop_loss_pct=float(risk.get("stop_loss_pct", 0.05)),
        min_cash_buffer_pct=float(risk.get("min_cash_buffer_pct", 0.05)),
        allow_fractional=bool(risk.get("allow_fractional", True)),
    )

    return TradingSettings(
        config_path=path,
        initial_cash=policy.initial_cash,
        monthly_profit_target=policy.monthly_profit_target,
        mode=mode,
        symbols=symbols,
        data_source=str(data.get("source", "robinhood_mcp")),
        csv_path=_repo_relative(base_path, str(data.get("csv_path", "data/sample_prices.csv"))),
        quote_snapshot_path=_repo_relative(
            base_path,
            str(data.get("quote_snapshot_path", "data/live_quotes/latest.json")),
        ),
        journal_path=_repo_relative(base_path, str(journal.get("path", "journal/trades.csv"))),
        strategy_name=str(strategy.get("name", "moving_average_crossover")),
        fast_window=int(strategy.get("fast_window", 10)),
        slow_window=int(strategy.get("slow_window", 30)),
        pair_strategy=load_pair_strategy_settings(pair_strategy),
        daytrade_strategy=load_daytrade_strategy_settings(daytrade_strategy),
        risk=policy,
        authorization=load_authorization_policy(authorization),
    )


def load_pair_strategy_settings(raw: dict[str, Any]) -> PairStrategySettings:
    return PairStrategySettings(
        name=str(raw.get("name", "soxl_soxs_rules")),
        fast_window=int(raw.get("fast_window", 5)),
        slow_window=int(raw.get("slow_window", 20)),
        min_confirmation_return_pct=float(raw.get("min_confirmation_return_pct", 0.5)),
        max_chase_return_pct=float(raw.get("max_chase_return_pct", 8.0)),
        order_amount=float(raw.get("order_amount", 25.0)),
        stop_loss_pct=float(raw.get("stop_loss_pct", 0.05)),
        take_profit_pct=float(raw.get("take_profit_pct", 0.08)),
        max_daily_notional=float(raw.get("max_daily_notional", 100.0)),
        max_monthly_realized_loss=float(raw.get("max_monthly_realized_loss", 20.0)),
    )


def load_daytrade_strategy_settings(raw: dict[str, Any]) -> DayTradeStrategySettings:
    return DayTradeStrategySettings(
        name=str(raw.get("name", "aggressive_soxl_soxs_daytrade")),
        lookback_window=int(raw.get("lookback_window", 3)),
        trend_window=int(raw.get("trend_window", 8)),
        min_session_move_pct=float(raw.get("min_session_move_pct", raw.get("min_gap_pct", 0.25))),
        min_prior_return_pct=float(raw.get("min_prior_return_pct", 1.0)),
        max_session_move_pct=float(raw.get("max_session_move_pct", raw.get("max_opening_gap_pct", 18.0))),
        live_entry_source=str(raw.get("live_entry_source", "premarket_confirmed_momentum")),
        require_fresh_history_for_live_entries=bool(raw.get("require_fresh_history_for_live_entries", True)),
        allow_stale_plan_live_fallback=bool(raw.get("allow_stale_plan_live_fallback", False)),
        stale_plan_min_session_move_pct=float(raw.get("stale_plan_min_session_move_pct", 4.0)),
        defensive_min_session_move_pct=float(raw.get("defensive_min_session_move_pct", 2.0)),
        order_amount=float(raw.get("order_amount", 100.0)),
        stop_loss_pct=float(raw.get("stop_loss_pct", 0.03)),
        take_profit_pct=float(raw.get("take_profit_pct", 0.08)),
        runner_enabled=bool(raw.get("runner_enabled", False)),
        initial_take_profit_pct=float(raw.get("initial_take_profit_pct", raw.get("take_profit_pct", 0.08))),
        initial_exit_fraction=float(raw.get("initial_exit_fraction", 1.0)),
        runner_stop_loss_pct=float(raw.get("runner_stop_loss_pct", 0.0)),
        runner_take_profit_pct=float(raw.get("runner_take_profit_pct", raw.get("take_profit_pct", 0.08))),
        runner_trailing_stop_pct=float(raw.get("runner_trailing_stop_pct", 0.0)),
        max_daily_notional=float(raw.get("max_daily_notional", 100.0)),
        max_monthly_realized_loss=float(raw.get("max_monthly_realized_loss", 20.0)),
    )


def load_authorization_policy(raw: dict[str, Any]) -> AuthorizationPolicy:
    if not raw or not bool(raw.get("enabled", False)):
        return AuthorizationPolicy.disabled()

    return AuthorizationPolicy(
        enabled=True,
        account_nickname=str(raw.get("account_nickname", "")),
        allowed_account_last4=str(raw.get("allowed_account_last4", "")),
        allowed_symbols=frozenset(str(symbol).upper() for symbol in raw.get("symbols", [])),
        allowed_market_hours=frozenset(str(value) for value in raw.get("market_hours", [])),
        time_in_force=str(raw.get("time_in_force", "gfd")).lower(),
        skip_review=bool(raw.get("skip_review", False)),
        max_buy_order_usd=float(raw.get("max_buy_order_usd", 0.0)),
        sell_to_close_symbols=frozenset(str(symbol).upper() for symbol in raw.get("sell_to_close_symbols", [])),
        max_opening_trades_per_day=int(raw.get("max_opening_trades_per_day", 0)),
        max_daily_notional_usd=float(raw.get("max_daily_notional_usd", 0.0)),
        max_monthly_realized_loss_usd=float(raw.get("max_monthly_realized_loss_usd", 0.0)),
        allow_options=bool(raw.get("allow_options", False)),
        allow_short_selling=bool(raw.get("allow_short_selling", False)),
        expires_on=parse_policy_date(str(raw["expires_on"])) if raw.get("expires_on") else None,
    )
