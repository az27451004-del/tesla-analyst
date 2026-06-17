import json
import tempfile
import unittest
from pathlib import Path

from stock_agent.collection import CollectionRequest, collect_data


class CollectionDedupTest(unittest.TestCase):
    def test_duplicate_news_events_are_merged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            events_path = Path(temp_dir) / "events.json"
            events_path.write_text(
                json.dumps(
                    [
                        {
                            "source": "Reuters",
                            "title": "Tesla announces delivery update",
                            "published_at": "2026-06-15T12:00:00Z",
                            "url": "https://example.test/same",
                        },
                        {
                            "source": "Bloomberg News",
                            "title": "Tesla announces delivery update",
                            "published_at": "2026-06-15T12:05:00Z",
                            "url": "https://example.test/same",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            request = CollectionRequest(
                symbol="TSLA",
                data_requirements=["news_events"],
                data_source_config={"local": {"enabled": True, "events_json": str(events_path)}},
            )

            result = collect_data(request)

            self.assertEqual(len(result.news_events), 1)
            dedup = result.news_events[0].raw_metadata["dedup"]
            self.assertEqual(dedup["source_count"], 2)
            self.assertIn("duplicates_merged", {warning.code for warning in result.warnings})

    def test_conflicting_market_data_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "prices.csv"
            csv_path.write_text(
                "date,close,source\n"
                "2026-06-15,100,Alpha Vantage\n"
                "2026-06-15,101,IBKR\n",
                encoding="utf-8",
            )
            request = CollectionRequest(
                symbol="TSLA",
                data_requirements=["market_data"],
                data_source_config={"local": {"enabled": True, "prices_csv": str(csv_path)}},
            )

            result = collect_data(request)

            self.assertEqual(len(result.conflicts), 1)
            self.assertEqual(result.conflicts[0].conflict_type, "market_data_price_conflict")
            self.assertTrue(result.conflicts[0].requires_review)


if __name__ == "__main__":
    unittest.main()

