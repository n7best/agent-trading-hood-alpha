from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .authorization import AuthorizationContext, TradeIntent
from .backtest import AggressiveDayTradeBacktester, Backtester, PairRulesBacktester
from .broker import LIVE_ACK_VALUE
from .config import TradingSettings, load_settings
from .data import CSVDataSource, combine_bars_csv, download_yfinance, load_nasdaq_history_json
from .journal import TradeJournal
from .market_data import RobinhoodMCPMarketData, write_quote_snapshot
from .models import LiveQuote
from .premarket import PREMARKET_QUOTE_SYMBOLS, build_premarket_plan
from .review import (
    build_daily_review,
    build_tuning_report,
    load_pair_history,
    load_quote_snapshot,
    tune_daytrade,
    write_review,
)
from .strategy import AggressiveSoxlSoxsDayTradeStrategy, MovingAverageCrossoverStrategy, SoxlSoxsRulesStrategy


def money(value: float) -> str:
    return f"${value:,.2f}"


def build_strategy(settings: TradingSettings) -> MovingAverageCrossoverStrategy:
    if settings.strategy_name != "moving_average_crossover":
        raise ValueError(f"Unsupported strategy: {settings.strategy_name}")
    return MovingAverageCrossoverStrategy(
        fast_window=settings.fast_window,
        slow_window=settings.slow_window,
    )


def print_warnings(settings: TradingSettings) -> None:
    warnings = settings.risk.warnings()
    if settings.mode == "live":
        warnings.append(
            "Live mode requested. It remains locked unless "
            f"TRADING_LIVE_ACK={LIVE_ACK_VALUE} is set."
        )
    for warning in warnings:
        print(f"WARNING: {warning}")


def format_quote(quote: LiveQuote, max_age_seconds: int) -> list[str]:
    lines = [
        f"Symbol: {quote.symbol}",
        f"Source: {quote.source}",
        f"Price: {money(quote.price)}",
        f"As of: {quote.as_of.isoformat()}",
        f"Age: {quote.age_seconds():.0f}s",
        f"State: {quote.state}",
        f"Has traded: {quote.has_traded}",
    ]
    if quote.bid is not None and quote.ask is not None:
        lines.append(f"Bid/ask: {money(quote.bid)} / {money(quote.ask)}")
        if quote.spread is not None:
            lines.append(f"Spread: {money(quote.spread)}")
    if quote.previous_close is not None:
        lines.append(f"Previous close: {money(quote.previous_close)}")
    if quote.daily_change_pct is not None:
        lines.append(f"Daily change: {quote.daily_change_pct:.2f}%")
    if quote.age_seconds() > max_age_seconds:
        lines.append(f"WARNING: Quote is older than {max_age_seconds}s; refresh with the MCP before trading.")
    if quote.state != "active" or not quote.has_traded:
        lines.append("WARNING: Quote is not in active traded state; do not treat it as executable.")
    return lines


def load_mcp_quote_for_symbol(settings: TradingSettings, symbol: str, input_path: str | None) -> LiveQuote:
    snapshot_path = Path(input_path).resolve() if input_path else settings.quote_snapshot_path
    quotes = RobinhoodMCPMarketData.load_snapshot(snapshot_path)
    try:
        return quotes[symbol.upper()]
    except KeyError as exc:
        available = ", ".join(sorted(quotes))
        raise SystemExit(f"No quote for {symbol.upper()} in {snapshot_path}. Available: {available}") from exc


def command_check(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    print(f"Config: {settings.config_path}")
    print(f"Mode: {settings.mode}")
    print(f"Symbols: {', '.join(settings.symbols)}")
    print(f"Data source: {settings.data_source}")
    print(f"MCP quote snapshot: {settings.quote_snapshot_path}")
    print(f"Historical CSV data: {settings.csv_path}")
    print(f"Journal: {settings.journal_path}")
    print(f"Pair strategy: {settings.pair_strategy.name}")
    print(
        "Pair strategy rules: "
        f"SMA {settings.pair_strategy.fast_window}/{settings.pair_strategy.slow_window}, "
        f"confirm {settings.pair_strategy.min_confirmation_return_pct:.2f}%, "
        f"max chase {settings.pair_strategy.max_chase_return_pct:.2f}%"
    )
    print(
        "Pair strategy risk: "
        f"order {money(settings.pair_strategy.order_amount)}, "
        f"stop {settings.pair_strategy.stop_loss_pct * 100:.2f}%, "
        f"take profit {settings.pair_strategy.take_profit_pct * 100:.2f}%"
    )
    print(f"Day-trade strategy: {settings.daytrade_strategy.name}")
    print(
        "Day-trade rules: "
        f"trend SMA {settings.daytrade_strategy.trend_window}, "
        f"lookback {settings.daytrade_strategy.lookback_window}, "
        f"session move {settings.daytrade_strategy.min_session_move_pct:.2f}%, "
        f"prior return {settings.daytrade_strategy.min_prior_return_pct:.2f}%"
    )
    history_text = (
        "requires fresh daily history"
        if settings.daytrade_strategy.require_fresh_history_for_live_entries
        else "does not block live entries solely on stale daily history"
    )
    print(
        "Day-trade live entry: "
        f"{settings.daytrade_strategy.live_entry_source}, "
        f"defensive threshold {settings.daytrade_strategy.defensive_min_session_move_pct:.2f}%, "
        f"{history_text}"
    )
    print(
        "Day-trade risk: "
        f"order {money(settings.daytrade_strategy.order_amount)}, "
        f"stop {settings.daytrade_strategy.stop_loss_pct * 100:.2f}%, "
        f"take profit {settings.daytrade_strategy.take_profit_pct * 100:.2f}%"
    )
    if settings.daytrade_strategy.runner_enabled:
        print(
            "Day-trade runner: "
            f"sell {settings.daytrade_strategy.initial_exit_fraction * 100:.0f}% "
            f"at {settings.daytrade_strategy.initial_take_profit_pct * 100:.2f}%, "
            f"runner stop {settings.daytrade_strategy.runner_stop_loss_pct * 100:.2f}%, "
            f"target {settings.daytrade_strategy.runner_take_profit_pct * 100:.2f}%, "
            f"trail {settings.daytrade_strategy.runner_trailing_stop_pct * 100:.2f}%"
        )
    for line in settings.authorization.summary_lines():
        print(line)
    print_warnings(settings)
    return 0


def command_plan(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    risk = settings.risk
    equity = settings.initial_cash
    print(f"Starting equity: {money(equity)}")
    print(f"Monthly target: {money(settings.monthly_profit_target)} ({risk.monthly_target_return_pct:.1f}%)")
    print(f"Max risk per trade: {money(risk.risk_budget(equity))}")
    print(f"Max position value: {money(risk.max_position_value(equity))}")
    print(f"Daily stop: {money(risk.daily_stop_amount(equity))}")
    print(f"Monthly stop: {money(risk.monthly_stop_amount(equity))}")
    print(f"Minimum cash buffer: {money(risk.min_cash_buffer(equity))}")
    print_warnings(settings)
    return 0


def command_backtest(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    symbol = (args.symbol or settings.symbols[0]).upper()
    data_path = Path(args.data).resolve() if args.data else settings.csv_path
    bars = CSVDataSource(data_path).load_bars(symbol)
    strategy = build_strategy(settings)
    result = Backtester(settings.risk, mode=settings.mode).run(bars, strategy)
    print(result.text_report())
    if args.write_journal:
        TradeJournal(settings.journal_path).append_fills(result.fills)
        print(f"Journal updated: {settings.journal_path}")
    return 0


def command_quote(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    symbol = (args.symbol or settings.symbols[0]).upper()
    quote = load_mcp_quote_for_symbol(settings, symbol, args.input)
    for line in format_quote(quote, args.max_age_seconds):
        print(line)
    return 0


def command_live_plan(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    symbol = (args.symbol or settings.symbols[0]).upper()
    quote = load_mcp_quote_for_symbol(settings, symbol, args.input)
    stop_price = args.stop_price if args.stop_price is not None else quote.price * (1 - settings.risk.stop_loss_pct)
    quantity = settings.risk.position_quantity(settings.initial_cash, quote.price, stop_price)
    notional = quantity * quote.price

    for line in format_quote(quote, args.max_age_seconds):
        print(line)
    print(f"Planned stop: {money(stop_price)}")
    print(f"Risk budget: {money(settings.risk.risk_budget(settings.initial_cash))}")
    print(f"Max position value: {money(settings.risk.max_position_value(settings.initial_cash))}")
    print(f"Suggested quantity: {quantity:.6f}")
    print(f"Estimated notional: {money(notional)}")
    print("Execution: use Robinhood MCP review_equity_order before any real order.")
    if symbol in settings.authorization.allowed_symbols:
        intent = TradeIntent(
            symbol=symbol,
            side="buy",
            order_type="market",
            dollar_amount=min(args.order_amount, settings.authorization.max_buy_order_usd),
            estimated_price=quote.price,
            market_hours=args.market_hours,
            time_in_force=settings.authorization.time_in_force,
        )
        context = AuthorizationContext(
            account_number=args.account_number or settings.authorization.allowed_account_last4,
            daily_notional_so_far=args.daily_notional_so_far,
            opening_trades_today=args.opening_trades_today,
            monthly_realized_loss=args.monthly_realized_loss,
        )
        errors = settings.authorization.validate(intent, context)
        if errors:
            print("Authorization: blocked")
            for error in errors:
                print(f"- {error}")
        else:
            print("Authorization: allowed")
    print_warnings(settings)
    return 0


def command_authorization(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    for line in settings.authorization.summary_lines():
        print(line)
    return 0


def command_authorize_intent(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    intent = TradeIntent(
        symbol=args.symbol,
        side=args.side,
        order_type=args.type,
        dollar_amount=args.dollar_amount,
        quantity=args.quantity,
        estimated_price=args.estimated_price,
        market_hours=args.market_hours,
        time_in_force=args.time_in_force,
        asset_class=args.asset_class,
        opens_position=not args.close_only,
    )
    context = AuthorizationContext(
        account_number=args.account_number,
        current_position_quantity=args.current_position_quantity,
        opening_trades_today=args.opening_trades_today,
        daily_notional_so_far=args.daily_notional_so_far,
        monthly_realized_loss=args.monthly_realized_loss,
    )
    errors = settings.authorization.validate(intent, context)
    if errors:
        print("Authorization: blocked")
        for error in errors:
            print(f"- {error}")
        return 2
    print("Authorization: allowed")
    return 0


def command_save_mcp_quotes(args: argparse.Namespace) -> int:
    payload = json.load(args.input)
    quotes = RobinhoodMCPMarketData.parse_quotes(payload)
    output = write_quote_snapshot(args.output, payload)
    print(f"Wrote {len(quotes)} Robinhood MCP quote(s) to {output}")
    return 0


def command_journal_summary(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    summary = TradeJournal(settings.journal_path).summary()
    print(f"Journal: {settings.journal_path}")
    for key, value in summary.items():
        label = key.replace("_", " ").title()
        if isinstance(value, float):
            if key.endswith("_pct"):
                print(f"{label}: {value:.2f}%")
            elif key.endswith("pnl"):
                print(f"{label}: {money(value)}")
            else:
                print(f"{label}: {value:.4f}")
        else:
            print(f"{label}: {value}")
    return 0


def command_download_data(args: argparse.Namespace) -> int:
    output = download_yfinance(args.symbol.upper(), args.period, args.output)
    print(f"Wrote {args.symbol.upper()} data to {output}")
    return 0


def command_import_nasdaq_history(args: argparse.Namespace) -> int:
    bars = load_nasdaq_history_json(args.input, args.symbol)
    combine_bars_csv(args.output, [bars])
    print(f"Wrote {len(bars)} {args.symbol.upper()} Nasdaq bars to {args.output}")
    return 0


def command_backtest_pair(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    pair_settings = settings.pair_strategy
    fast_window = args.fast_window if args.fast_window is not None else pair_settings.fast_window
    slow_window = args.slow_window if args.slow_window is not None else pair_settings.slow_window
    min_confirmation_return_pct = (
        args.min_confirmation_return_pct
        if args.min_confirmation_return_pct is not None
        else pair_settings.min_confirmation_return_pct
    )
    max_chase_return_pct = (
        args.max_chase_return_pct
        if args.max_chase_return_pct is not None
        else pair_settings.max_chase_return_pct
    )
    order_amount = args.order_amount if args.order_amount is not None else pair_settings.order_amount
    stop_loss_pct = args.stop_loss_pct if args.stop_loss_pct is not None else pair_settings.stop_loss_pct
    take_profit_pct = args.take_profit_pct if args.take_profit_pct is not None else pair_settings.take_profit_pct
    max_daily_notional = (
        args.max_daily_notional
        if args.max_daily_notional is not None
        else pair_settings.max_daily_notional
    )
    max_monthly_realized_loss = (
        args.max_monthly_realized_loss
        if args.max_monthly_realized_loss is not None
        else pair_settings.max_monthly_realized_loss
    )
    soxl_bars = CSVDataSource(args.soxl_data).load_bars("SOXL")
    soxs_bars = CSVDataSource(args.soxs_data).load_bars("SOXS")
    strategy = SoxlSoxsRulesStrategy(
        fast_window=fast_window,
        slow_window=slow_window,
        min_confirmation_return_pct=min_confirmation_return_pct,
        max_chase_return_pct=max_chase_return_pct,
    )
    result = PairRulesBacktester(
        policy=settings.risk,
        order_amount=order_amount,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        max_daily_notional=max_daily_notional,
        max_monthly_realized_loss=max_monthly_realized_loss,
        mode=settings.mode,
    ).run({"SOXL": soxl_bars, "SOXS": soxs_bars}, strategy)

    print("Rules:")
    print(f"- Trade SOXL when SOXL SMA {fast_window}>{slow_window} and daily return >= {min_confirmation_return_pct:.2f}%")
    print(f"- Trade SOXS when SOXL SMA {fast_window}<{slow_window} and daily return <= -{min_confirmation_return_pct:.2f}%")
    print(f"- Skip entries when abs(SOXL daily return) > {max_chase_return_pct:.2f}%")
    print(f"- One open position at a time; exit on target change, {stop_loss_pct * 100:.2f}% stop, or {take_profit_pct * 100:.2f}% take-profit")
    print(f"- Order amount {money(order_amount)}, daily notional cap {money(max_daily_notional)}")
    print()
    print(result.text_report())
    if args.write_journal:
        TradeJournal(settings.journal_path).append_fills(result.fills)
        print(f"Journal updated: {settings.journal_path}")
    return 0


def command_backtest_daytrade(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    day_settings = settings.daytrade_strategy
    lookback_window = args.lookback_window if args.lookback_window is not None else day_settings.lookback_window
    trend_window = args.trend_window if args.trend_window is not None else day_settings.trend_window
    min_session_move_pct = (
        args.min_session_move_pct
        if args.min_session_move_pct is not None
        else day_settings.min_session_move_pct
    )
    min_prior_return_pct = (
        args.min_prior_return_pct
        if args.min_prior_return_pct is not None
        else day_settings.min_prior_return_pct
    )
    max_session_move_pct = (
        args.max_session_move_pct
        if args.max_session_move_pct is not None
        else day_settings.max_session_move_pct
    )
    order_amount = args.order_amount if args.order_amount is not None else day_settings.order_amount
    stop_loss_pct = args.stop_loss_pct if args.stop_loss_pct is not None else day_settings.stop_loss_pct
    take_profit_pct = args.take_profit_pct if args.take_profit_pct is not None else day_settings.take_profit_pct
    max_daily_notional = (
        args.max_daily_notional
        if args.max_daily_notional is not None
        else day_settings.max_daily_notional
    )
    max_monthly_realized_loss = (
        args.max_monthly_realized_loss
        if args.max_monthly_realized_loss is not None
        else day_settings.max_monthly_realized_loss
    )

    soxl_bars = CSVDataSource(args.soxl_data).load_bars("SOXL")
    soxs_bars = CSVDataSource(args.soxs_data).load_bars("SOXS")
    strategy = AggressiveSoxlSoxsDayTradeStrategy(
        lookback_window=lookback_window,
        trend_window=trend_window,
        min_session_move_pct=min_session_move_pct,
        min_prior_return_pct=min_prior_return_pct,
        max_session_move_pct=max_session_move_pct,
    )
    result = AggressiveDayTradeBacktester(
        policy=settings.risk,
        order_amount=order_amount,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        max_daily_notional=max_daily_notional,
        max_monthly_realized_loss=max_monthly_realized_loss,
        mode=settings.mode,
    ).run({"SOXL": soxl_bars, "SOXS": soxs_bars}, strategy)

    print("Aggressive day-trade rules:")
    history_text = (
        "requires fresh daily history"
        if day_settings.require_fresh_history_for_live_entries
        else "does not block solely because daily CSV history is stale"
    )
    print("- Live monitor: evaluate entries throughout regular hours on each scheduled check; no open-only rule")
    print(
        f"- Live entry source: {day_settings.live_entry_source}; "
        f"use fresh Robinhood session move plus current-date premarket direction, {history_text}"
    )
    if day_settings.allow_stale_plan_live_fallback:
        print(
            "- Stale premarket fallback: enabled only for fresh live quotes with "
            f"abs(SOXL session move) >= {day_settings.stale_plan_min_session_move_pct:.2f}%; "
            "broker/account/authorization/risk checks still apply"
        )
    else:
        print("- Stale premarket fallback: disabled; stale plans block opening buys")
    print("- Daily backtest proxy: uses daily OHLC bars, so fills are approximated with the same day's open")
    print(f"- Buy SOXL when prior SOXL close is above SMA {trend_window} and current session move >= {min_session_move_pct:.2f}% or {lookback_window}-bar prior return >= {min_prior_return_pct:.2f}%")
    print(f"- Buy SOXS when prior SOXL close is below SMA {trend_window} and current session move <= -{min_session_move_pct:.2f}% or {lookback_window}-bar prior return <= -{min_prior_return_pct:.2f}%")
    print(f"- Defensive risk mode requires live session move confirmation of {day_settings.defensive_min_session_move_pct:.2f}%")
    print(f"- Skip entries when abs(SOXL session move) > {max_session_move_pct:.2f}%")
    print(f"- Same-day exit: {stop_loss_pct * 100:.2f}% stop, {take_profit_pct * 100:.2f}% take-profit, otherwise close")
    print("- If stop and take-profit both touch inside the same daily bar, assume the stop hits first")
    print(f"- Order amount {money(order_amount)}, daily notional cap {money(max_daily_notional)}")
    print()
    print(result.text_report())
    if args.write_journal:
        TradeJournal(settings.journal_path).append_fills(result.fills)
        print(f"Journal updated: {settings.journal_path}")
    return 0


def command_daily_review(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    bars_by_symbol = load_pair_history(args.soxl_data, args.soxs_data)
    quotes = load_quote_snapshot(args.quote_input or settings.quote_snapshot_path)
    content = build_daily_review(settings, bars_by_symbol, quotes)
    if args.write_report or args.output:
        output = args.output or f"reports/daily/{date.today().isoformat()}.md"
        written = write_review(output, content)
        print(f"Wrote daily review: {written}")
    print(content)
    return 0


def command_premarket_plan(args: argparse.Namespace) -> int:
    if args.symbols:
        print(",".join(PREMARKET_QUOTE_SYMBOLS))
        return 0
    settings = load_settings(args.config)
    quotes = load_quote_snapshot(args.quote_input or settings.quote_snapshot_path)
    content = build_premarket_plan(settings, quotes)
    if args.write_report or args.output:
        output = args.output or f"reports/premarket/{date.today().isoformat()}.md"
        written = write_review(output, content)
        latest = write_review("reports/premarket/latest.md", content)
        print(f"Wrote premarket plan: {written}")
        print(f"Wrote latest premarket plan: {latest}")
    print(content)
    return 0


def command_tune_daytrade(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    bars_by_symbol = load_pair_history(args.soxl_data, args.soxs_data)
    results = tune_daytrade(settings, bars_by_symbol)
    content = build_tuning_report(results, top=args.top)
    if args.write_report or args.output:
        output = args.output or f"reports/tuning/daytrade-{date.today().isoformat()}.md"
        written = write_review(output, content)
        print(f"Wrote tuning report: {written}")
    print(content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper-first trading toolkit")
    parser.add_argument("--config", default="config/trading.toml", help="Path to trading config TOML")
    subparsers = parser.add_subparsers(dest="command", required=False)

    check = subparsers.add_parser("check", help="Validate config and print warnings")
    check.set_defaults(func=command_check)

    plan = subparsers.add_parser("plan", help="Print account target and risk budget")
    plan.set_defaults(func=command_plan)

    backtest = subparsers.add_parser("backtest", help="Run a CSV-data backtest")
    backtest.add_argument("--symbol", help="Symbol to test; defaults to the first configured symbol")
    backtest.add_argument("--data", help="CSV data path; defaults to configured data.csv_path")
    backtest.add_argument("--write-journal", action="store_true", help="Append simulated fills to the journal")
    backtest.set_defaults(func=command_backtest)

    quote = subparsers.add_parser("quote", help="Read a Robinhood MCP quote snapshot and print current quote context")
    quote.add_argument("--symbol", help="Symbol to quote; defaults to the first configured symbol")
    quote.add_argument("--input", help="Path to raw Robinhood MCP get_equity_quotes JSON")
    quote.add_argument("--max-age-seconds", type=int, default=900)
    quote.set_defaults(func=command_quote)

    live_plan = subparsers.add_parser("live-plan", help="Size a trade from a Robinhood MCP quote snapshot")
    live_plan.add_argument("--symbol", help="Symbol to size; defaults to the first configured symbol")
    live_plan.add_argument("--input", help="Path to raw Robinhood MCP get_equity_quotes JSON")
    live_plan.add_argument("--stop-price", type=float, help="Explicit stop price; defaults to configured stop_loss_pct")
    live_plan.add_argument("--order-amount", type=float, default=100.0, help="Dollar amount to validate against authorization")
    live_plan.add_argument("--market-hours", default="regular_hours", choices=["regular_hours", "extended_hours", "all_day_hours"])
    live_plan.add_argument("--account-number", help="Full runtime account number; config stores only last four")
    live_plan.add_argument("--daily-notional-so-far", type=float, default=0.0)
    live_plan.add_argument("--opening-trades-today", type=int, default=0)
    live_plan.add_argument("--monthly-realized-loss", type=float, default=0.0)
    live_plan.add_argument("--max-age-seconds", type=int, default=900)
    live_plan.set_defaults(func=command_live_plan)

    authorization = subparsers.add_parser("authorization", help="Print standing live-trade authorization policy")
    authorization.set_defaults(func=command_authorization)

    authorize_intent = subparsers.add_parser("authorize-intent", help="Validate a proposed order against standing authorization")
    authorize_intent.add_argument("--account-number", required=True)
    authorize_intent.add_argument("--symbol", required=True)
    authorize_intent.add_argument("--side", required=True, choices=["buy", "sell"])
    authorize_intent.add_argument("--type", default="market", choices=["market", "limit", "stop_market", "stop_limit"])
    authorize_intent.add_argument("--time-in-force", default="gfd")
    authorize_intent.add_argument("--market-hours", default="regular_hours", choices=["regular_hours", "extended_hours", "all_day_hours"])
    authorize_intent.add_argument("--dollar-amount", type=float)
    authorize_intent.add_argument("--quantity", type=float)
    authorize_intent.add_argument("--estimated-price", type=float)
    authorize_intent.add_argument("--asset-class", default="equity")
    authorize_intent.add_argument("--close-only", action="store_true")
    authorize_intent.add_argument("--current-position-quantity", type=float, default=0.0)
    authorize_intent.add_argument("--daily-notional-so-far", type=float, default=0.0)
    authorize_intent.add_argument("--opening-trades-today", type=int, default=0)
    authorize_intent.add_argument("--monthly-realized-loss", type=float, default=0.0)
    authorize_intent.set_defaults(func=command_authorize_intent)

    save_quotes = subparsers.add_parser("save-mcp-quotes", help="Validate and save raw Robinhood MCP quote JSON from stdin")
    save_quotes.add_argument("--output", required=True)
    save_quotes.add_argument("input", nargs="?", type=argparse.FileType("r"), default=sys.stdin)
    save_quotes.set_defaults(func=command_save_mcp_quotes)

    journal = subparsers.add_parser("journal-summary", help="Summarize the configured trade journal")
    journal.set_defaults(func=command_journal_summary)

    download = subparsers.add_parser("download-data", help="Download CSV data with optional yfinance dependency")
    download.add_argument("--symbol", required=True)
    download.add_argument("--period", default="1y")
    download.add_argument("--output", required=True)
    download.set_defaults(func=command_download_data)

    import_nasdaq = subparsers.add_parser("import-nasdaq-history", help="Convert Nasdaq historical JSON to tradebot CSV")
    import_nasdaq.add_argument("--symbol", required=True)
    import_nasdaq.add_argument("--input", required=True)
    import_nasdaq.add_argument("--output", required=True)
    import_nasdaq.set_defaults(func=command_import_nasdaq_history)

    pair = subparsers.add_parser("backtest-pair", help="Backtest the SOXL/SOXS standing rules")
    pair.add_argument("--soxl-data", default="data/history/soxl.csv")
    pair.add_argument("--soxs-data", default="data/history/soxs.csv")
    pair.add_argument("--order-amount", type=float)
    pair.add_argument("--max-daily-notional", type=float)
    pair.add_argument("--max-monthly-realized-loss", type=float)
    pair.add_argument("--stop-loss-pct", type=float)
    pair.add_argument("--take-profit-pct", type=float)
    pair.add_argument("--fast-window", type=int)
    pair.add_argument("--slow-window", type=int)
    pair.add_argument("--min-confirmation-return-pct", type=float)
    pair.add_argument("--max-chase-return-pct", type=float)
    pair.add_argument("--write-journal", action="store_true")
    pair.set_defaults(func=command_backtest_pair)

    daytrade = subparsers.add_parser("backtest-daytrade", help="Backtest aggressive SOXL/SOXS same-day rules")
    daytrade.add_argument("--soxl-data", default="data/history/soxl.csv")
    daytrade.add_argument("--soxs-data", default="data/history/soxs.csv")
    daytrade.add_argument("--lookback-window", type=int)
    daytrade.add_argument("--trend-window", type=int)
    daytrade.add_argument("--min-session-move-pct", "--min-gap-pct", dest="min_session_move_pct", type=float)
    daytrade.add_argument("--min-prior-return-pct", type=float)
    daytrade.add_argument("--max-session-move-pct", "--max-opening-gap-pct", dest="max_session_move_pct", type=float)
    daytrade.add_argument("--order-amount", type=float)
    daytrade.add_argument("--max-daily-notional", type=float)
    daytrade.add_argument("--max-monthly-realized-loss", type=float)
    daytrade.add_argument("--stop-loss-pct", type=float)
    daytrade.add_argument("--take-profit-pct", type=float)
    daytrade.add_argument("--write-journal", action="store_true")
    daytrade.set_defaults(func=command_backtest_daytrade)

    daily_review = subparsers.add_parser("daily-review", help="Generate the daily SOXL/SOXS review report")
    daily_review.add_argument("--soxl-data", default="data/history/soxl.csv")
    daily_review.add_argument("--soxs-data", default="data/history/soxs.csv")
    daily_review.add_argument("--quote-input", help="Path to Robinhood MCP quote snapshot JSON")
    daily_review.add_argument("--write-report", action="store_true")
    daily_review.add_argument("--output")
    daily_review.set_defaults(func=command_daily_review)

    premarket = subparsers.add_parser("premarket-plan", help="Generate a SOXL/SOXS premarket session plan")
    premarket.add_argument("--quote-input", help="Path to Robinhood MCP quote snapshot JSON")
    premarket.add_argument("--write-report", action="store_true")
    premarket.add_argument("--output")
    premarket.add_argument(
        "--symbols",
        action="store_true",
        help="Print the preferred quote basket for the premarket automation",
    )
    premarket.set_defaults(func=command_premarket_plan)

    tune = subparsers.add_parser("tune-daytrade", help="Run a bounded aggressive day-trade parameter sweep")
    tune.add_argument("--soxl-data", default="data/history/soxl.csv")
    tune.add_argument("--soxs-data", default="data/history/soxs.csv")
    tune.add_argument("--top", type=int, default=10)
    tune.add_argument("--write-report", action="store_true")
    tune.add_argument("--output")
    tune.set_defaults(func=command_tune_daytrade)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        args.func = command_plan
    return args.func(args)
