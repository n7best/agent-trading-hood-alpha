import unittest
from datetime import datetime, timezone

from tradebot.config import load_settings
from tradebot.models import LiveQuote
from tradebot.premarket import assess_premarket, build_premarket_plan


def quote(symbol: str, price: float, previous_close: float) -> LiveQuote:
    return LiveQuote(
        symbol=symbol,
        price=price,
        previous_close=previous_close,
        as_of=datetime(2026, 6, 9, 12, 45, tzinfo=timezone.utc),
        source="test",
        state="active",
        has_traded=True,
    )


class PremarketPlanTests(unittest.TestCase):
    def test_blocks_extreme_soxl_session_move(self):
        settings = load_settings()
        assessment = assess_premarket(
            settings,
            {
                "SOXL": quote("SOXL", 160, 200),
                "SOXS": quote("SOXS", 7.2, 6.0),
                "QQQ": quote("QQQ", 490, 500),
                "SMH": quote("SMH", 240, 250),
            },
        )

        self.assertEqual(assessment.risk_mode, "blocked")
        self.assertEqual(assessment.allowed_entry_symbols, ())
        self.assertEqual(assessment.monitor_cadence_minutes, 15)

    def test_bearish_semiconductor_plan_allows_soxs_only(self):
        settings = load_settings()
        assessment = assess_premarket(
            settings,
            {
                "SOXL": quote("SOXL", 194, 200),
                "SOXS": quote("SOXS", 6.2, 6.0),
                "QQQ": quote("QQQ", 494, 500),
                "SMH": quote("SMH", 246, 250),
            },
        )

        self.assertEqual(assessment.bias, "bearish-semiconductors")
        self.assertEqual(assessment.risk_mode, "normal")
        self.assertEqual(assessment.allowed_entry_symbols, ("SOXS",))

    def test_mixed_plan_keeps_watch_cadence(self):
        settings = load_settings()
        plan = build_premarket_plan(
            settings,
            {
                "SOXL": quote("SOXL", 201, 200),
                "SOXS": quote("SOXS", 5.9, 6.0),
                "QQQ": quote("QQQ", 499, 500),
                "SMH": quote("SMH", 251, 250),
            },
        )

        self.assertIn("Risk mode: watch", plan)
        self.assertIn("Planned monitor cadence: 10 minutes", plan)

    def test_large_confirmed_move_is_defensive(self):
        settings = load_settings()
        assessment = assess_premarket(
            settings,
            {
                "SOXL": quote("SOXL", 176, 200),
                "SOXS": quote("SOXS", 6.7, 6.0),
                "QQQ": quote("QQQ", 490, 500),
                "SMH": quote("SMH", 238, 250),
            },
        )

        self.assertEqual(assessment.bias, "bearish-semiconductors")
        self.assertEqual(assessment.risk_mode, "defensive")
        self.assertEqual(assessment.monitor_cadence_minutes, 10)
        self.assertEqual(assessment.allowed_entry_symbols, ("SOXS",))


if __name__ == "__main__":
    unittest.main()
