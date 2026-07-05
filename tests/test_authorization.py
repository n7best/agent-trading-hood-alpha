import unittest
from datetime import date
from dataclasses import replace

from tradebot.authorization import AuthorizationContext, TradeIntent
from tradebot.config import load_settings


AUTHORIZED_TEST_ACCOUNT = "000006375"


class AuthorizationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_settings("config/trading.toml").authorization

    def test_allows_bounded_soxl_buy(self):
        errors = self.policy.validate(
            TradeIntent(
                symbol="SOXL",
                side="buy",
                order_type="market",
                time_in_force="gfd",
                market_hours="regular_hours",
                dollar_amount=250,
                estimated_price=250,
            ),
            AuthorizationContext(account_number=AUTHORIZED_TEST_ACCOUNT, trade_date=date(2026, 6, 10)),
        )

        self.assertEqual(errors, [])

    def test_blocks_order_above_daily_notional(self):
        errors = self.policy.validate(
            TradeIntent(
                symbol="SOXL",
                side="buy",
                order_type="market",
                time_in_force="gfd",
                market_hours="regular_hours",
                dollar_amount=200,
            ),
            AuthorizationContext(
                account_number=AUTHORIZED_TEST_ACCOUNT,
                trade_date=date(2026, 6, 10),
                daily_notional_so_far=150,
            ),
        )

        self.assertTrue(any("daily notional" in error for error in errors))

    def test_allows_soxs_sell_to_close(self):
        errors = self.policy.validate(
            TradeIntent(
                symbol="SOXS",
                side="sell",
                order_type="market",
                time_in_force="gfd",
                market_hours="regular_hours",
                quantity=1,
                estimated_price=10,
                opens_position=False,
            ),
            AuthorizationContext(
                account_number=AUTHORIZED_TEST_ACCOUNT,
                trade_date=date(2026, 6, 10),
                current_position_quantity=2,
            ),
        )

        self.assertEqual(errors, [])

    def test_blocks_dollar_order_in_extended_hours(self):
        errors = self.policy.validate(
            TradeIntent(
                symbol="SOXL",
                side="buy",
                order_type="market",
                time_in_force="gfd",
                market_hours="extended_hours",
                dollar_amount=25,
            ),
            AuthorizationContext(account_number=AUTHORIZED_TEST_ACCOUNT, trade_date=date(2026, 6, 10)),
        )

        self.assertTrue(any("regular_hours" in error for error in errors))

    def test_allows_without_configured_expiration(self):
        errors = self.policy.validate(
            TradeIntent(
                symbol="SOXL",
                side="buy",
                order_type="market",
                time_in_force="gfd",
                market_hours="regular_hours",
                dollar_amount=10,
            ),
            AuthorizationContext(account_number=AUTHORIZED_TEST_ACCOUNT, trade_date=date(2026, 6, 16)),
        )

        self.assertEqual(errors, [])

    def test_blocks_after_expiration_when_configured(self):
        policy = replace(self.policy, expires_on=date(2026, 6, 15))
        errors = policy.validate(
            TradeIntent(
                symbol="SOXL",
                side="buy",
                order_type="market",
                time_in_force="gfd",
                market_hours="regular_hours",
                dollar_amount=10,
            ),
            AuthorizationContext(account_number=AUTHORIZED_TEST_ACCOUNT, trade_date=date(2026, 6, 16)),
        )

        self.assertTrue(any("expired" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
