import unittest

from tradebot.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_daytrade_runner_settings_load_from_config(self):
        daytrade = load_settings("config/trading.toml").daytrade_strategy

        self.assertEqual(daytrade.lookback_window, 2)
        self.assertEqual(daytrade.trend_window, 8)
        self.assertAlmostEqual(daytrade.min_prior_return_pct, 3.0)
        self.assertAlmostEqual(daytrade.stop_loss_pct, 0.03)
        self.assertAlmostEqual(daytrade.take_profit_pct, 0.08)
        self.assertTrue(daytrade.runner_enabled)
        self.assertAlmostEqual(daytrade.initial_take_profit_pct, 0.03)
        self.assertAlmostEqual(daytrade.initial_exit_fraction, 0.5)
        self.assertAlmostEqual(daytrade.runner_stop_loss_pct, 0.0)
        self.assertAlmostEqual(daytrade.runner_take_profit_pct, 0.08)
        self.assertAlmostEqual(daytrade.runner_trailing_stop_pct, 0.02)


if __name__ == "__main__":
    unittest.main()
