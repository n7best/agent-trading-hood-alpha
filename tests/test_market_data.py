import unittest
from datetime import datetime, timezone

from tradebot.market_data import RobinhoodMCPMarketData, parse_robinhood_time


class RobinhoodMCPMarketDataTests(unittest.TestCase):
    def test_parse_recorded_quote_snapshot(self):
        quotes = RobinhoodMCPMarketData.load_snapshot("tests/fixtures/robinhood_spy_quote.json")
        quote = quotes["SPY"]

        self.assertEqual(quote.symbol, "SPY")
        self.assertEqual(quote.source, "robinhood_mcp")
        self.assertAlmostEqual(quote.price, 743.49)
        self.assertAlmostEqual(quote.bid, 743.50)
        self.assertAlmostEqual(quote.ask, 743.53)
        self.assertAlmostEqual(quote.previous_close, 737.55)
        self.assertEqual(quote.state, "active")
        self.assertTrue(quote.has_traded)
        self.assertAlmostEqual(quote.daily_change_pct, 0.805369, places=5)

    def test_uses_newer_non_regular_trade_when_available(self):
        payload = {
            "data": {
                "results": [
                    {
                        "quote": {
                            "symbol": "ABC",
                            "last_trade_price": "10.00",
                            "venue_last_trade_time": "2026-06-08T20:00:00Z",
                            "last_non_reg_trade_price": "10.25",
                            "venue_last_non_reg_trade_time": "2026-06-08T20:05:00Z",
                            "adjusted_previous_close": "9.50",
                            "has_traded": "true",
                            "state": "active",
                        }
                    }
                ]
            }
        }

        quote = RobinhoodMCPMarketData.parse_quotes(payload)["ABC"]
        self.assertEqual(quote.price, 10.25)
        self.assertEqual(quote.as_of, datetime(2026, 6, 8, 20, 5, tzinfo=timezone.utc))

    def test_uses_adjusted_previous_close_for_split_adjusted_quotes(self):
        payload = {
            "data": {
                "results": [
                    {
                        "quote": {
                            "symbol": "SOXS",
                            "last_trade_price": "45.930000",
                            "venue_last_trade_time": "2026-07-15T19:59:59.775087197Z",
                            "last_non_reg_trade_price": "45.960000",
                            "venue_last_non_reg_trade_time": "2026-07-15T20:32:27.512927877Z",
                            "adjusted_previous_close": "42.800000",
                            "previous_close": "4.280000",
                            "has_traded": True,
                            "state": "active",
                        },
                        "close": {
                            "symbol": "SOXS",
                            "date": "2026-07-14",
                            "price": "4.28",
                            "source": "consolidated-unadjusted",
                        },
                    }
                ]
            }
        }

        quote = RobinhoodMCPMarketData.parse_quotes(payload)["SOXS"]
        self.assertAlmostEqual(quote.previous_close, 42.8)
        self.assertAlmostEqual(quote.daily_change_pct, 7.383177570093466)

    def test_parse_robinhood_time_returns_utc(self):
        parsed = parse_robinhood_time("2026-06-08T15:49:33.868764675Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
