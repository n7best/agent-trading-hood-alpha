import unittest
from datetime import datetime, timedelta, timezone

from tradebot.backtest import AggressiveDayTradeBacktester, PairRulesBacktester
from tradebot.data import load_nasdaq_history_json
from tradebot.models import Bar, LiveQuote
from tradebot.risk import RiskPolicy
from tradebot.strategy import (
    AggressiveSoxlSoxsDayTradeStrategy,
    SoxlSoxsRulesStrategy,
    generate_live_momentum_signal,
)


def make_pair_bars():
    start = datetime(2026, 1, 1)
    soxl_prices = [
        20, 20.2, 20.4, 20.6, 20.8, 21.0, 21.3, 21.7, 22.1, 22.5,
        22.9, 23.4, 23.9, 24.3, 24.8, 25.2, 25.5, 25.8, 26.1, 26.4,
        27.0, 27.5, 28.0, 27.2, 26.0, 25.0, 24.0, 23.0, 22.5, 22.0,
    ]
    soxs_prices = [
        12, 11.9, 11.8, 11.7, 11.6, 11.5, 11.3, 11.1, 10.9, 10.7,
        10.5, 10.3, 10.1, 10.0, 9.8, 9.7, 9.6, 9.5, 9.4, 9.3,
        9.1, 8.9, 8.8, 9.2, 9.8, 10.4, 11.0, 11.6, 12.1, 12.5,
    ]

    def bars(symbol, prices):
        return [
            Bar(
                timestamp=start + timedelta(days=index),
                symbol=symbol,
                open=price,
                high=price * 1.04,
                low=price * 0.96,
                close=price,
                volume=1000,
            )
            for index, price in enumerate(prices)
        ]

    return {"SOXL": bars("SOXL", soxl_prices), "SOXS": bars("SOXS", soxs_prices)}


def make_live_quote(symbol, price, previous_close):
    return LiveQuote(
        symbol=symbol,
        price=price,
        previous_close=previous_close,
        as_of=datetime(2026, 6, 12, 15, 0, tzinfo=timezone.utc),
        source="test",
        state="active",
        has_traded=True,
    )


class SoxlSoxsRulesTests(unittest.TestCase):
    def test_nasdaq_history_parser(self):
        bars = load_nasdaq_history_json("tests/fixtures/nasdaq_soxl_sample.json", "SOXL")
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].timestamp, datetime(2026, 6, 4))
        self.assertAlmostEqual(bars[0].close, 262.70)

    def test_pair_strategy_generates_backtest_result(self):
        bars_by_symbol = make_pair_bars()
        strategy = SoxlSoxsRulesStrategy(fast_window=3, slow_window=8, max_chase_return_pct=12)
        result = PairRulesBacktester(
            RiskPolicy(initial_cash=500),
            order_amount=25,
            stop_loss_pct=0.05,
            take_profit_pct=0.08,
        ).run(bars_by_symbol, strategy)

        self.assertEqual(result.symbol, "SOXL/SOXS")
        self.assertGreater(len(result.equity_curve), 0)
        self.assertIn("signal_days", result.metrics)

    def test_aggressive_daytrade_backtest_is_flat_each_day(self):
        bars_by_symbol = make_pair_bars()
        strategy = AggressiveSoxlSoxsDayTradeStrategy(
            lookback_window=2,
            trend_window=4,
            min_session_move_pct=0,
            min_prior_return_pct=0.5,
            max_session_move_pct=20,
        )
        result = AggressiveDayTradeBacktester(
            RiskPolicy(initial_cash=500),
            order_amount=100,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
        ).run(bars_by_symbol, strategy)

        self.assertEqual(result.symbol, "SOXL/SOXS DAY")
        self.assertGreater(result.metrics["day_trades"], 0)
        self.assertEqual(result.metrics["fills"], result.metrics["day_trades"] * 2)

    def test_live_momentum_allows_soxl_without_history(self):
        signal = generate_live_momentum_signal(
            make_live_quote("SOXL", 108, 100),
            make_live_quote("SOXS", 9.20, 10),
            allowed_symbols=("SOXL",),
            risk_mode="normal",
            min_session_move_pct=0.25,
            max_session_move_pct=18,
        )

        self.assertEqual(signal.target_symbol, "SOXL")
        self.assertEqual(signal.price, 108)
        self.assertIn("live momentum long SOXL", signal.reason)

    def test_live_momentum_blocks_direction_not_allowed_by_plan(self):
        signal = generate_live_momentum_signal(
            make_live_quote("SOXL", 92, 100),
            make_live_quote("SOXS", 10.80, 10),
            allowed_symbols=("SOXL",),
            risk_mode="normal",
            min_session_move_pct=0.25,
            max_session_move_pct=18,
        )

        self.assertIsNone(signal.target_symbol)
        self.assertIn("plan does not allow SOXS", signal.reason)

    def test_defensive_live_momentum_requires_stronger_move(self):
        signal = generate_live_momentum_signal(
            make_live_quote("SOXL", 101, 100),
            make_live_quote("SOXS", 9.90, 10),
            allowed_symbols=("SOXL",),
            risk_mode="defensive",
            min_session_move_pct=0.25,
            max_session_move_pct=18,
            defensive_min_session_move_pct=2,
        )

        self.assertIsNone(signal.target_symbol)
        self.assertIn("threshold 2.00%", signal.reason)

    def test_stale_plan_blocks_by_default(self):
        signal = generate_live_momentum_signal(
            make_live_quote("SOXL", 108, 100),
            make_live_quote("SOXS", 9.20, 10),
            allowed_symbols=(),
            risk_mode="stale",
            min_session_move_pct=0.25,
            max_session_move_pct=18,
        )

        self.assertIsNone(signal.target_symbol)
        self.assertIn("risk mode stale blocks", signal.reason)

    def test_stale_plan_fallback_allows_strong_live_momentum(self):
        signal = generate_live_momentum_signal(
            make_live_quote("SOXL", 108, 100),
            make_live_quote("SOXS", 9.20, 10),
            allowed_symbols=(),
            risk_mode="stale",
            min_session_move_pct=0.25,
            max_session_move_pct=18,
            allow_stale_plan_live_fallback=True,
            stale_plan_min_session_move_pct=4,
        )

        self.assertEqual(signal.target_symbol, "SOXL")
        self.assertIn("fallback long SOXL", signal.reason)

    def test_stale_plan_fallback_still_requires_stronger_move(self):
        signal = generate_live_momentum_signal(
            make_live_quote("SOXL", 102, 100),
            make_live_quote("SOXS", 9.80, 10),
            allowed_symbols=(),
            risk_mode="stale",
            min_session_move_pct=0.25,
            max_session_move_pct=18,
            allow_stale_plan_live_fallback=True,
            stale_plan_min_session_move_pct=4,
        )

        self.assertIsNone(signal.target_symbol)
        self.assertIn("threshold 4.00%", signal.reason)


if __name__ == "__main__":
    unittest.main()
