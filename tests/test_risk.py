import unittest

from tradebot.risk import RiskPolicy


class RiskPolicyTests(unittest.TestCase):
    def test_position_quantity_uses_trade_risk_and_position_cap(self):
        policy = RiskPolicy(initial_cash=500, max_risk_per_trade_pct=0.01, max_position_value_pct=0.25)
        quantity = policy.position_quantity(equity=500, price=100, stop_price=95)
        self.assertEqual(quantity, 1.0)

    def test_monthly_target_warning_for_twenty_percent_goal(self):
        policy = RiskPolicy(initial_cash=500, monthly_profit_target=100)
        self.assertGreaterEqual(policy.monthly_target_return_pct, 20)
        self.assertTrue(any("aggressive" in warning for warning in policy.warnings()))


if __name__ == "__main__":
    unittest.main()

