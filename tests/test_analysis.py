import json
import unittest

from stock_agent.analysis import DRIVER_DELIVERY, DRIVER_MACRO, DRIVER_NARRATIVE, analyze_collection, analyze_market_events
from stock_agent.collection.models import (
    CollectionResult,
    CollectionSummary,
    DataQualityReport,
    FilingEvent,
    NewsEvent,
    PricePoint as CollectionPricePoint,
    WarningRecord,
)
from tsla_agent.models import Event, PricePoint


class AnalysisLayerTest(unittest.TestCase):
    def test_event_maps_to_driver(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[Event(source="Reuters", title="Tesla deliveries beat consensus with record growth")],
        )

        self.assertEqual(analysis.event_signals[0].driver, DRIVER_DELIVERY)
        self.assertGreater(analysis.driver_scores[DRIVER_DELIVERY], 0)

    def test_missing_data_degrades_confidence(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[],
            events=[],
            missing_requirements=["macro_data", "financial_metrics", "options_data"],
        )

        self.assertEqual(analysis.confidence_level, "LOW")
        self.assertEqual(analysis.data_coverage.confidence_cap, "LOW")
        self.assertTrue(any("缺少价格数据" in item for item in analysis.quality_downgrades))
        self.assertTrue(any("宏观数据" in item for item in analysis.quality_downgrades))

    def test_analysis_layer_does_not_emit_trade_plan_fields(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 8)],
            events=[Event(source="test", title="Fed rate concern weighs on Nasdaq growth stocks")],
        )

        payload = json.dumps(analysis.to_dict(), ensure_ascii=False)

        self.assertIn(DRIVER_MACRO, payload)
        self.assertNotIn("buy_signal", payload)
        self.assertNotIn("sell_signal", payload)
        self.assertNotIn("trade_plan", payload)
        self.assertNotIn("generated_target_price", payload)

    def test_analyze_collection_consumes_collection_result(self):
        result = CollectionResult(
            collection_summary=CollectionSummary(symbol="tsla"),
            market_data=[
                CollectionPricePoint(
                    date_time=f"2026-06-{day:02d}",
                    close=100 + day,
                    high=101 + day,
                    low=99 + day,
                    volume=1000 + day,
                    source="local",
                )
                for day in range(1, 22)
            ],
            news_events=[
                NewsEvent(
                    title="Robotaxi approval improves AI narrative",
                    summary_raw="Analysts say the milestone improves the long-term AI narrative.",
                    source="Reuters",
                    source_reliability=0.75,
                )
            ],
            warnings=[WarningRecord(message="Manual review required for source freshness.")],
            data_quality_report=DataQualityReport(missing_requirements=["macro_data"]),
        )

        analysis = analyze_collection(result)
        payload = json.dumps(analysis.to_dict(), ensure_ascii=False)

        self.assertEqual(analysis.symbol, "TSLA")
        self.assertEqual(analysis.event_signals[0].driver, DRIVER_NARRATIVE)
        self.assertIn("Manual review", "\n".join(analysis.quality_downgrades))
        self.assertNotIn("trade_plan", payload)

    def test_analysis_accepts_mapping_inputs(self):
        analysis = analyze_market_events(
            symbol="tsla",
            prices=[
                {
                    "date_time": f"2026-06-{day:02d}",
                    "close": 100 + day,
                    "high": 102 + day,
                    "low": 98 + day,
                    "volume": 1000,
                    "source": "sample",
                }
                for day in range(1, 22)
            ],
            events=[
                {
                    "title": "Robotaxi milestone improves AI narrative",
                    "summary_raw": "Sample event for compatibility testing.",
                    "event_type": "news",
                    "source": "manual",
                    "source_reliability": 0.5,
                }
            ],
            warnings=["Sample data compatibility test."],
        )

        self.assertEqual(analysis.symbol, "TSLA")
        self.assertEqual(analysis.event_signals[0].driver, DRIVER_NARRATIVE)
        self.assertEqual(analysis.confidence_level, "LOW")

    def test_ai_driver_requires_word_boundary_or_explicit_phrase(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(title="Billionaire investor changes capital allocation", source="test", source_reliability=0.3),
                NewsEvent(title="Tesla AI chip team sets new wafer intelligence target", source="Reuters", source_reliability=0.75),
            ],
        )

        by_title = {signal.title: signal for signal in analysis.event_signals}
        self.assertNotEqual(by_title["Billionaire investor changes capital allocation"].driver, DRIVER_NARRATIVE)
        self.assertEqual(by_title["Tesla AI chip team sets new wafer intelligence target"].driver, DRIVER_NARRATIVE)

    def test_sec_filing_types_are_classified_and_capped(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                FilingEvent(filing_type="4", title="4 filing: Statement of changes in beneficial ownership", source="SEC EDGAR", source_reliability=1.0),
                FilingEvent(filing_type="10-Q", title="10-Q filing: Quarterly report", source="SEC EDGAR", source_reliability=1.0),
            ],
        )

        by_title = {signal.title: signal for signal in analysis.event_signals}
        form4 = by_title["4 filing: Statement of changes in beneficial ownership"]
        tenq = by_title["10-Q filing: Quarterly report"]

        self.assertLessEqual(form4.impact_score, 0.38)
        self.assertEqual(tenq.driver, "毛利率/EPS/现金流")
        self.assertLessEqual(tenq.impact_score, 0.62)

    def test_low_relevance_event_impact_is_capped(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(
                    title="Peer automaker stock rises while Tesla is mentioned",
                    source="test",
                    source_reliability=0.75,
                    raw_metadata={"requested_symbol_relevance": 0.4},
                )
            ],
        )

        self.assertLessEqual(analysis.event_signals[0].impact_score, 0.55)


if __name__ == "__main__":
    unittest.main()
