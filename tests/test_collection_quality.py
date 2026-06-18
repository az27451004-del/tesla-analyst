import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_agent.collection import CollectionRequest, collect_data
from stock_agent.collection.models import WarningRecord, now_iso
from stock_agent.collection.sources.sec_edgar import SECEdgarSource
from stock_agent.collection.sources.base import SourceOutput


class CollectionQualityTest(unittest.TestCase):
    def test_unknown_source_reliability_is_capped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            events_path = Path(temp_dir) / "events.json"
            events_path.write_text(
                json.dumps(
                    [
                        {
                            "source": "Mystery Blog",
                            "source_reliability": 0.99,
                            "title": "Unverified production rumor",
                            "published_at": "2026-06-15",
                        }
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
            self.assertLessEqual(result.news_events[0].source_reliability, 0.30)

    def test_sample_data_triggers_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            events_path = Path(temp_dir) / "events.json"
            events_path.write_text(
                json.dumps(
                    [
                        {
                            "source": "sample",
                            "title": "Fictional sample event",
                            "summary": "Sample only.",
                            "url": "https://example.com/sample",
                        }
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

            self.assertIn("sample_data_detected", {warning.code for warning in result.warnings})
            self.assertEqual(result.data_quality_report.overall_quality, "LOW")

    def test_missing_market_data_degrades_quality(self):
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["market_data"],
            data_source_config={},
        )

        result = collect_data(request)

        self.assertIn("market_data", result.data_quality_report.missing_requirements)
        self.assertEqual(result.data_quality_report.overall_quality, "INSUFFICIENT")
        self.assertFalse(result.data_quality_report.can_generate_analysis)

    def test_missing_data_requirements_are_recorded(self):
        request = CollectionRequest(symbol="TSLA", data_requirements=[], data_source_config={})

        result = collect_data(request)

        self.assertIn("data_requirements", result.data_quality_report.missing_requirements)
        self.assertIn("missing_data_requirements", {warning.code for warning in result.warnings})

    def test_source_failure_does_not_interrupt_other_sources(self):
        class BadSource:
            name = "bad"
            source_type = "test"

            def collect(self, request):
                raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as temp_dir:
            events_path = Path(temp_dir) / "events.json"
            events_path.write_text(json.dumps([{"source": "Reuters", "title": "Valid local item"}]), encoding="utf-8")
            request = CollectionRequest(
                symbol="TSLA",
                data_requirements=["news_events"],
                data_source_config={
                    "bad": {"enabled": True},
                    "local": {"enabled": True, "events_json": str(events_path)},
                },
            )

            with patch.dict("stock_agent.collection.collector.SOURCE_FACTORIES", {"bad": BadSource}):
                result = collect_data(request)

            self.assertEqual(len(result.news_events), 1)
            self.assertIn("bad", result.collection_summary.data_sources_failed)
            self.assertIn("data_source_failed", {warning.code for warning in result.warnings})

    def test_alpha_vantage_falls_back_from_premium_adjusted_endpoint(self):
        responses = [
            {"Information": "This is a premium endpoint."},
            {
                "Time Series (Daily)": {
                    "2026-06-15": {
                        "1. open": "100",
                        "2. high": "110",
                        "3. low": "99",
                        "4. close": "108",
                        "5. volume": "12345",
                    }
                }
            },
        ]

        def fake_get_json(params):
            self.assertIn(params["function"], {"TIME_SERIES_DAILY_ADJUSTED", "TIME_SERIES_DAILY"})
            return responses.pop(0)

        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["market_data"],
            data_source_config={"alpha_vantage": {"enabled": True, "api_key": "test-key"}},
        )

        with patch("stock_agent.collection.sources.alpha_vantage._get_json", side_effect=fake_get_json):
            result = collect_data(request)

        self.assertEqual(len(result.market_data), 1)
        self.assertEqual(result.market_data[0].close, 108.0)
        self.assertEqual(result.market_data[0].raw_metadata["function"], "TIME_SERIES_DAILY")

    def test_alpha_vantage_filters_low_relevance_news(self):
        payload = {
            "feed": [
                {
                    "title": "Rice Hall James trims Applied Optoelectronics stake",
                    "summary": "Institutional filing focused on AAOI.",
                    "source": "MarketBeat",
                    "time_published": "20260615T120000",
                    "url": "https://example.test/aaoi",
                    "ticker_sentiment": [
                        {"ticker": "AAOI", "relevance_score": "1.000000", "ticker_sentiment_score": "-0.2"},
                        {"ticker": "TSLA", "relevance_score": "0.629161", "ticker_sentiment_score": "0.1"},
                    ],
                },
                {
                    "title": "Tesla expands robotaxi testing",
                    "summary": "Tesla update directly mentions the company.",
                    "source": "Reuters",
                    "time_published": "20260615T130000",
                    "url": "https://example.test/tesla",
                    "ticker_sentiment": [
                        {"ticker": "TSLA", "relevance_score": "0.400000", "ticker_sentiment_score": "0.3"},
                    ],
                },
                {
                    "title": "BYD price cuts raise competitive pressure",
                    "summary": "High relevance peer news for EV investors.",
                    "source": "CNBC",
                    "time_published": "20260615T140000",
                    "url": "https://example.test/byd",
                    "ticker_sentiment": [
                        {"ticker": "BYDDF", "relevance_score": "1.000000", "ticker_sentiment_score": "-0.1"},
                        {"ticker": "TSLA", "relevance_score": "0.810000", "ticker_sentiment_score": "-0.2"},
                    ],
                },
            ]
        }

        request = CollectionRequest(
            symbol="TSLA",
            company_name="Tesla, Inc.",
            data_requirements=["news_events"],
            data_source_config={"alpha_vantage": {"enabled": True, "api_key": "test-key"}},
        )

        with patch("stock_agent.collection.sources.alpha_vantage._get_json", return_value=payload):
            result = collect_data(request)

        titles = {event.title for event in result.news_events}
        self.assertNotIn("Rice Hall James trims Applied Optoelectronics stake", titles)
        self.assertIn("Tesla expands robotaxi testing", titles)
        self.assertIn("BYD price cuts raise competitive pressure", titles)

        direct = next(event for event in result.news_events if event.title.startswith("Tesla expands"))
        self.assertTrue(direct.raw_metadata["direct_symbol_match"])
        self.assertEqual(direct.raw_metadata["requested_symbol_relevance"], 0.4)

        peer = next(event for event in result.news_events if event.title.startswith("BYD price cuts"))
        self.assertFalse(peer.raw_metadata["direct_symbol_match"])
        self.assertEqual(peer.raw_metadata["requested_symbol_relevance"], 0.81)

    def test_sec_filings_get_chinese_titles_and_metadata(self):
        payload = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K", "4"],
                    "filingDate": ["2026-06-15", "2026-06-14", "2026-06-13"],
                    "reportDate": ["2026-03-31", "", ""],
                    "accessionNumber": ["0001", "0002", "0003"],
                    "primaryDocument": ["tsla-10q.htm", "tsla-8k.htm", "form4.xml"],
                    "primaryDocDescription": ["FORM 10-Q", "FORM 8-K", "OWNERSHIP DOCUMENT"],
                }
            }
        }

        filings = SECEdgarSource()._parse_filings(payload, "0001318605", 3, now_iso(), "Tesla, Inc.")

        self.assertIn("季度财报（10-Q）", filings[0].title)
        self.assertEqual(filings[0].raw_metadata["display_group"], "财报披露")
        self.assertEqual(filings[0].raw_metadata["sec_importance"], "core")
        self.assertIn("10-Q filing: FORM 10-Q", filings[0].raw_metadata["original_title"])
        self.assertIn("重大事项报告（8-K）", filings[1].title)
        self.assertEqual(filings[1].raw_metadata["display_group"], "重大披露")
        self.assertIn("内部人持股变动（Form 4）", filings[2].title)
        self.assertEqual(filings[2].raw_metadata["display_group"], "持股/登记类披露")


if __name__ == "__main__":
    unittest.main()
