import json
import unittest

from stock_agent.analysis import DRIVER_DELIVERY, DRIVER_MACRO, DRIVER_NARRATIVE, analyze_collection, analyze_market_events
from stock_agent.collection.models import (
    CollectionResult,
    CollectionSummary,
    DataQualityReport,
    FilingEvent,
    IndustryEvent,
    MacroPoint,
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

        signal = analysis.event_signals[0]
        self.assertEqual(signal.driver, DRIVER_DELIVERY)
        self.assertIn("交付、库存和价格", signal.impact_reason)
        self.assertIn("最终影响分", "；".join(signal.score_breakdown))
        self.assertTrue(signal.counterpoint)
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

    def test_financial_news_driver_classification_rules(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(title="JPMorgan revisits TSLA stock rating", source="Reuters", source_reliability=0.75),
                NewsEvent(title="Cathie Wood sold Tesla stock to buy SpaceX", source="Yahoo Finance", source_reliability=0.75),
                NewsEvent(title="Electric vehicle growth slowing after U.S. support withdrawn", source="Seeking Alpha", source_reliability=0.6),
                NewsEvent(title="Tesla FSD robotaxi approval expands in Europe", source="Reuters", source_reliability=0.75),
            ],
        )

        by_title = {signal.title: signal for signal in analysis.event_signals}
        self.assertEqual(by_title["JPMorgan revisits TSLA stock rating"].driver, "估值/安全边际")
        self.assertEqual(by_title["Cathie Wood sold Tesla stock to buy SpaceX"].driver, "技术面/期权/资金流")
        self.assertEqual(by_title["Electric vehicle growth slowing after U.S. support withdrawn"].driver, "监管/诉讼/政策")
        self.assertEqual(by_title["Electric vehicle growth slowing after U.S. support withdrawn"].direction, "负面")
        self.assertEqual(by_title["Tesla FSD robotaxi approval expands in Europe"].driver, DRIVER_NARRATIVE)

    def test_delivery_forecast_news_maps_to_delivery_driver(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(title="Goldman Sachs raises Tesla stock delivery forecast on Europe strength", source="Investing.com", source_reliability=0.6),
            ],
        )

        self.assertEqual(analysis.event_signals[0].driver, DRIVER_DELIVERY)
        self.assertEqual(analysis.event_signals[0].direction, "正面")
        self.assertIn("未提供可量化数值", analysis.event_signals[0].quantitative_evidence[0])
        self.assertGreater(analysis.driver_scores[DRIVER_DELIVERY], 0)

    def test_event_signal_explains_narrative_direction_and_missing_quant_data(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(
                    title="Tesla FSD robotaxi approval expands in Europe",
                    source="Reuters",
                    source_reliability=0.75,
                ),
            ],
        )

        signal = analysis.event_signals[0]
        self.assertEqual(signal.driver, DRIVER_NARRATIVE)
        self.assertEqual(signal.direction, "正面")
        self.assertIn("自动驾驶商业化", signal.impact_reason)
        self.assertIn("未提供可量化数值", signal.quantitative_evidence[0])
        self.assertIn("监管限制", signal.counterpoint)
        self.assertIn("关键词情绪", "；".join(signal.score_breakdown))

    def test_raises_concerns_is_negative_regulatory_not_positive_raise(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(
                    title="TSLA Stock Falls - Senator Raises Concerns Over Tesla's Misleading FSD Safety Data",
                    source="Reuters",
                    source_reliability=0.75,
                ),
            ],
        )

        signal = analysis.event_signals[0]
        self.assertEqual(signal.driver, "监管/诉讼/政策")
        self.assertEqual(signal.direction, "负面")
        self.assertIn("raises concerns", "；".join(signal.score_breakdown + (signal.impact_reason,)).lower())

    def test_policy_conflict_title_is_negative(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(
                    title="'Elon Is Scared Of This Conversation': Democrat Fires Back At Musk's Subsidy Defense",
                    source="Yahoo Finance",
                    source_reliability=0.75,
                ),
            ],
        )

        signal = analysis.event_signals[0]
        self.assertEqual(signal.driver, "监管/诉讼/政策")
        self.assertEqual(signal.direction, "负面")

    def test_event_signal_carries_quantitative_metadata(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                NewsEvent(
                    title="Tesla deliveries beat consensus with record growth",
                    source="local",
                    source_reliability=0.7,
                    raw_metadata={"deliveries": 460000, "yoy_change_pct": 12.0, "consensus": 445000},
                )
            ],
        )

        evidence = "；".join(analysis.event_signals[0].quantitative_evidence)
        self.assertIn("交付量：460000", evidence)
        self.assertIn("同比变化：12.0", evidence)
        self.assertIn("一致预期：445000", evidence)

    def test_structured_macro_data_scores_macro_driver(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[],
            macro_data=[
                MacroPoint(indicator_name="10Y Treasury Yield", value=4.6, source="FRED", source_reliability=0.95),
                MacroPoint(indicator_name="2Y Treasury Yield", value=4.2, source="FRED", source_reliability=0.95),
            ],
        )

        self.assertLess(analysis.driver_scores[DRIVER_MACRO], 0)

    def test_structured_industry_delivery_data_scores_delivery_driver(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[],
            industry_data=[
                IndustryEvent(
                    title_or_metric="Tesla quarterly deliveries growth",
                    value=460000,
                    source="local",
                    raw_metadata={"yoy_change_pct": 12.0},
                )
            ],
        )

        self.assertGreater(analysis.driver_scores[DRIVER_DELIVERY], 0)

    def test_low_priority_sec_filings_rank_below_core_disclosures(self):
        analysis = analyze_market_events(
            symbol="TSLA",
            prices=[PricePoint(date=f"2026-06-{day:02d}", close=100 + day, volume=1000) for day in range(1, 22)],
            events=[
                FilingEvent(
                    filing_type="4",
                    title="内部人持股变动（Form 4）：Tesla, Inc. 最新披露",
                    summary_raw="董事、高管或大股东持股变动披露。",
                    source="SEC EDGAR",
                    source_reliability=1.0,
                    raw_metadata={"sec_importance": "low"},
                ),
                FilingEvent(
                    filing_type="8-K",
                    title="重大事项报告（8-K）：Tesla, Inc. 最新披露",
                    summary_raw="公司重大事项或临时事件披露。",
                    source="SEC EDGAR",
                    source_reliability=1.0,
                    raw_metadata={"sec_importance": "material"},
                ),
                FilingEvent(
                    filing_type="10-Q",
                    title="季度财报（10-Q）：Tesla, Inc. 最新披露",
                    summary_raw="公司季度财务与经营情况披露。",
                    source="SEC EDGAR",
                    source_reliability=1.0,
                    raw_metadata={"sec_importance": "core"},
                ),
            ],
        )

        by_title = {signal.title: signal for signal in analysis.event_signals}
        self.assertLess(by_title["内部人持股变动（Form 4）：Tesla, Inc. 最新披露"].impact_score, 0.30)
        self.assertGreater(
            by_title["季度财报（10-Q）：Tesla, Inc. 最新披露"].impact_score,
            by_title["内部人持股变动（Form 4）：Tesla, Inc. 最新披露"].impact_score,
        )


if __name__ == "__main__":
    unittest.main()
