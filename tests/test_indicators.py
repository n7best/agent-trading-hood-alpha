import unittest

from tradebot.indicators import max_drawdown_pct, simple_moving_average


class IndicatorTests(unittest.TestCase):
    def test_simple_moving_average(self):
        self.assertEqual(
            simple_moving_average([1, 2, 3, 4, 5], 3),
            [None, None, 2.0, 3.0, 4.0],
        )

    def test_max_drawdown_pct(self):
        self.assertAlmostEqual(max_drawdown_pct([100, 110, 99, 120]), 10.0)


if __name__ == "__main__":
    unittest.main()

