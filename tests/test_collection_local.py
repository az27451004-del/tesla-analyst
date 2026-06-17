import json
import tempfile
import unittest
from pathlib import Path

from stock_agent.collection import CollectionRequest, collect_data


class CollectionLocalTest(unittest.TestCase):
    def test_local_csv_reads_market_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "prices.csv"
            csv_path.write_text(
                "date,open,high,low,close,adjusted_close,volume,source\n"
                "2026-06-15,100,110,99,108,107.5,12345,Alpha Vantage\n",
                encoding="utf-8",
            )
            request = CollectionRequest(
                symbol="tsla",
                market="US",
                data_requirements=["market_data"],
                data_source_config={"local": {"enabled": True, "prices_csv": str(csv_path)}},
            )

            result = collect_data(request)

            self.assertEqual(len(result.market_data), 1)
            point = result.market_data[0]
            self.assertEqual(point.close, 108.0)
            self.assertEqual(point.volume, 12345.0)
            self.assertEqual(point.raw_metadata["symbol"], "TSLA")
            self.assertEqual(point.source_reliability, 0.90)

    def test_local_json_reads_news_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            events_path = Path(temp_dir) / "events.json"
            events_path.write_text(
                json.dumps(
                    [
                        {
                            "source": "Reuters",
                            "title": "Company announces production update",
                            "summary": "Raw factual item.",
                            "published_at": "2026-06-15",
                            "url": "https://example.test/news",
                            "category": "company_update",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            request = CollectionRequest(
                symbol="tsla",
                market="US",
                data_requirements=["news_events"],
                data_source_config={"local": {"enabled": True, "events_json": str(events_path)}},
            )

            result = collect_data(request)

            self.assertEqual(len(result.news_events), 1)
            event = result.news_events[0]
            self.assertEqual(event.title, "Company announces production update")
            self.assertEqual(event.related_symbols, ["TSLA"])
            self.assertGreaterEqual(event.source_reliability, 0.75)

    def test_module_does_not_generate_trading_outputs(self):
        request = CollectionRequest(
            symbol="TSLA",
            market="US",
            data_requirements=["news_events"],
            data_source_config={},
        )

        result_json = collect_data(request).to_json()

        self.assertNotIn("buy_signal", result_json)
        self.assertNotIn("sell_signal", result_json)
        self.assertNotIn("trade_plan", result_json)
        self.assertNotIn("generated_target_price", result_json)


if __name__ == "__main__":
    unittest.main()

