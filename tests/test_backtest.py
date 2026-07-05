import unittest
from datetime import datetime, timedelta

from tradebot.backtest import Backtester
from tradebot.models import Bar
from tradebot.risk import RiskPolicy
from tradebot.strategy import MovingAverageCrossoverStrategy


def make_bars(prices):
    start = datetime(2026, 1, 1)
    return [
        Bar(
            timestamp=start + timedelta(days=index),
            symbol="TST",
            open=price,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000,
        )
        for index, price in enumerate(prices)
    ]


class BacktesterTests(unittest.TestCase):
    def test_backtest_produces_metrics(self):
        prices = [10, 10, 10, 10, 11, 12, 13, 14, 13, 12, 11, 10, 9, 8]
        bars = make_bars(prices)
        strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=4)
        policy = RiskPolicy(initial_cash=500, max_risk_per_trade_pct=0.01, max_position_value_pct=0.25)
        result = Backtester(policy).run(bars, strategy)

        self.assertEqual(result.symbol, "TST")
        self.assertGreater(len(result.equity_curve), 0)
        self.assertIn("total_return_pct", result.metrics)
        self.assertIn("max_drawdown_pct", result.metrics)


if __name__ == "__main__":
    unittest.main()

