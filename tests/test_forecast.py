import unittest

from tsla_agent.forecast import forecast_price_path, summarize_market
from tsla_agent.models import PricePoint


class ForecastTest(unittest.TestCase):
    def test_forecast_generates_requested_horizons(self):
        prices = [PricePoint(date=f"2026-01-{day:02d}", close=100 + day) for day in range(1, 31)]

        forecast = forecast_price_path(prices, event_sentiment_tilt=0.25, horizons=(1, 5, 20))

        self.assertIn(forecast.signal, {"偏多", "偏空", "震荡"})
        self.assertEqual([point.horizon_days for point in forecast.points], [1, 5, 20])
        self.assertTrue(all(point.base_price > 0 for point in forecast.points))

    def test_market_summary_handles_missing_prices(self):
        summary = summarize_market("TSLA", [])

        self.assertIsNone(summary.last_close)
        self.assertEqual(summary.trend_label, "无价格数据")


if __name__ == "__main__":
    unittest.main()
