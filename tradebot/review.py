from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .backtest import AggressiveDayTradeBacktester, PairRulesBacktester
from .config import TradingSettings
from .data import CSVDataSource
from .market_data import RobinhoodMCPMarketData
from .models import BacktestResult, LiveQuote
from .strategy import AggressiveSoxlSoxsDayTradeStrategy, SoxlSoxsRulesStrategy


@dataclass(frozen=True)
class TuningResult:
    final_equity: float
    realized_pnl: float
    max_drawdown_pct: float
    profit_factor: float | None
    closed_trades: int
    trend_window: int
    lookback_window: int
    min_session_move_pct: float
    min_prior_return_pct: float
    stop_loss_pct: float
    take_profit_pct: float


def load_pair_history(soxl_path: str | Path, soxs_path: str | Path):
    return {
        "SOXL": CSVDataSource(soxl_path).load_bars("SOXL"),
        "SOXS": CSVDataSource(soxs_path).load_bars("SOXS"),
    }


def run_configured_pair_backtest(settings: TradingSettings, bars_by_symbol) -> BacktestResult:
    pair = settings.pair_strategy
    strategy = SoxlSoxsRulesStrategy(
        fast_window=pair.fast_window,
        slow_window=pair.slow_window,
        min_confirmation_return_pct=pair.min_confirmation_return_pct,
        max_chase_return_pct=pair.max_chase_return_pct,
    )
    return PairRulesBacktester(
        policy=settings.risk,
        order_amount=pair.order_amount,
        stop_loss_pct=pair.stop_loss_pct,
        take_profit_pct=pair.take_profit_pct,
        max_daily_notional=pair.max_daily_notional,
        max_monthly_realized_loss=pair.max_monthly_realized_loss,
        mode=settings.mode,
    ).run(bars_by_symbol, strategy)


def run_configured_daytrade_backtest(settings: TradingSettings, bars_by_symbol) -> BacktestResult:
    day = settings.daytrade_strategy
    strategy = AggressiveSoxlSoxsDayTradeStrategy(
        lookback_window=day.lookback_window,
        trend_window=day.trend_window,
        min_session_move_pct=day.min_session_move_pct,
        min_prior_return_pct=day.min_prior_return_pct,
        max_session_move_pct=day.max_session_move_pct,
    )
    return AggressiveDayTradeBacktester(
        policy=settings.risk,
        order_amount=day.order_amount,
        stop_loss_pct=day.stop_loss_pct,
        take_profit_pct=day.take_profit_pct,
        max_daily_notional=day.max_daily_notional,
        max_monthly_realized_loss=day.max_monthly_realized_loss,
        mode=settings.mode,
    ).run(bars_by_symbol, strategy)


def load_quote_snapshot(path: str | Path) -> dict[str, LiveQuote]:
    try:
        return RobinhoodMCPMarketData.load_snapshot(path)
    except FileNotFoundError:
        return {}


def summarize_result(name: str, result: BacktestResult) -> list[str]:
    profit_factor = result.metrics.get("profit_factor")
    profit_factor_text = "n/a" if profit_factor is None else f"{profit_factor:.4f}"
    return [
        f"### {name}",
        "",
        f"- Final equity: ${result.final_equity:,.2f}",
        f"- Realized PnL: ${result.realized_pnl:,.2f}",
        f"- Total return: {float(result.metrics.get('total_return_pct') or 0):.2f}%",
        f"- Max drawdown: {float(result.metrics.get('max_drawdown_pct') or 0):.2f}%",
        f"- Closed trades: {int(result.metrics.get('closed_trades') or 0)}",
        f"- Win rate: {float(result.metrics.get('win_rate_pct') or 0):.2f}%",
        f"- Profit factor: {profit_factor_text}",
    ]


def build_daily_review(
    settings: TradingSettings,
    bars_by_symbol,
    quotes: dict[str, LiveQuote],
    review_date: date | None = None,
) -> str:
    review_date = review_date or date.today()
    baseline = run_configured_pair_backtest(settings, bars_by_symbol)
    aggressive = run_configured_daytrade_backtest(settings, bars_by_symbol)
    lines = [
        f"# Daily Trading Review - {review_date.isoformat()}",
        "",
        "## Scope",
        "",
        "- Symbols: SOXL, SOXS",
        "- Live execution: disabled inside this report",
        "- Order review preference: governed by standing authorization",
        "- Data note: backtests use daily OHLC history; aggressive day-trade rules are an intraday proxy",
        "",
        "## Quote Snapshot",
        "",
    ]

    if quotes:
        for symbol in sorted(quotes):
            quote = quotes[symbol]
            change = quote.daily_change_pct
            change_text = "n/a" if change is None else f"{change:.2f}%"
            lines.append(
                f"- {symbol}: ${quote.price:,.2f} as of {quote.as_of.isoformat()} "
                f"({change_text} vs previous close, state={quote.state})"
            )
    else:
        lines.append("- No quote snapshot available.")

    lines.extend(["", "## Backtest Snapshot", ""])
    lines.extend(summarize_result("Conservative Pair Rules", baseline))
    lines.extend([""])
    lines.extend(summarize_result("Aggressive Day-Trade Proxy", aggressive))
    lines.extend(["", "## Review Flags", ""])

    flags = review_flags(baseline, aggressive)
    lines.extend(f"- {flag}" for flag in flags)
    return "\n".join(lines) + "\n"


def review_flags(baseline: BacktestResult, aggressive: BacktestResult) -> list[str]:
    flags: list[str] = []
    aggressive_pf = aggressive.metrics.get("profit_factor")
    aggressive_dd = float(aggressive.metrics.get("max_drawdown_pct") or 0.0)
    aggressive_return = float(aggressive.metrics.get("total_return_pct") or 0.0)
    if aggressive_return < 0:
        flags.append("Aggressive day-trade proxy is negative; disable live aggressive entries until retuned.")
    if aggressive_pf is None or aggressive_pf < 1.1:
        flags.append("Aggressive day-trade profit factor is weak; run parameter sweep before changing size.")
    if aggressive_dd > 8:
        flags.append("Aggressive day-trade drawdown exceeds 8%; reduce size or tighten filters.")
    if aggressive.final_equity <= baseline.final_equity:
        flags.append("Aggressive rules do not outperform conservative baseline; prefer baseline.")
    if not flags:
        flags.append("No immediate tuning trigger from current daily-history proxy.")
    return flags


def write_review(path: str | Path, content: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content)
    return output


def tune_daytrade(
    settings: TradingSettings,
    bars_by_symbol,
    trend_windows: Iterable[int] = (5, 8, 13, 20),
    lookback_windows: Iterable[int] = (2, 3, 5),
    min_session_moves: Iterable[float] = (0.0, 0.25, 0.5, 1.0),
    min_prior_returns: Iterable[float] = (0.0, 1.0, 2.0, 3.0),
    stops: Iterable[float] = (0.02, 0.03, 0.04, 0.05),
    take_profits: Iterable[float] = (0.04, 0.06, 0.08, 0.10),
) -> list[TuningResult]:
    results: list[TuningResult] = []
    day = settings.daytrade_strategy
    for trend in trend_windows:
        for lookback in lookback_windows:
            for session_move in min_session_moves:
                for prior in min_prior_returns:
                    for stop in stops:
                        for take in take_profits:
                            if take <= stop:
                                continue
                            strategy = AggressiveSoxlSoxsDayTradeStrategy(
                                lookback_window=lookback,
                                trend_window=trend,
                                min_session_move_pct=session_move,
                                min_prior_return_pct=prior,
                                max_session_move_pct=day.max_session_move_pct,
                            )
                            result = AggressiveDayTradeBacktester(
                                policy=settings.risk,
                                order_amount=day.order_amount,
                                stop_loss_pct=stop,
                                take_profit_pct=take,
                                max_daily_notional=day.max_daily_notional,
                                max_monthly_realized_loss=day.max_monthly_realized_loss,
                                mode=settings.mode,
                            ).run(bars_by_symbol, strategy)
                            results.append(
                                TuningResult(
                                    final_equity=result.final_equity,
                                    realized_pnl=result.realized_pnl,
                                    max_drawdown_pct=float(result.metrics.get("max_drawdown_pct") or 0.0),
                                    profit_factor=result.metrics.get("profit_factor"),
                                    closed_trades=int(result.metrics.get("closed_trades") or 0),
                                    trend_window=trend,
                                    lookback_window=lookback,
                                    min_session_move_pct=session_move,
                                    min_prior_return_pct=prior,
                                    stop_loss_pct=stop,
                                    take_profit_pct=take,
                                )
                            )
    results.sort(key=lambda item: (item.final_equity, -item.max_drawdown_pct), reverse=True)
    return results


def build_tuning_report(results: list[TuningResult], top: int = 10) -> str:
    lines = [
        f"# Day-Trade Tuning Sweep - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Rank | Final Equity | PnL | Max DD | PF | Trades | Trend | Lookback | Session Move | Prior | Stop | Take |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for index, result in enumerate(results[:top], start=1):
        pf = "" if result.profit_factor is None else f"{result.profit_factor:.4f}"
        lines.append(
            f"| {index} | ${result.final_equity:.2f} | ${result.realized_pnl:.2f} | "
            f"{result.max_drawdown_pct:.2f}% | {pf} | {result.closed_trades} | "
            f"{result.trend_window} | {result.lookback_window} | {result.min_session_move_pct:.2f}% | "
            f"{result.min_prior_return_pct:.2f}% | {result.stop_loss_pct * 100:.2f}% | "
            f"{result.take_profit_pct * 100:.2f}% |"
        )
    return "\n".join(lines) + "\n"
