import json
import tempfile
import unittest
from pathlib import Path

from stock_agent.cli import main
from stock_agent.collection.models import (
    CollectionResult,
    CollectionSummary,
    DataQualityReport,
    FilingEvent,
    MacroPoint,
    NewsEvent,
    PricePoint,
    SourceRecord,
)


class AnalysisReportTest(unittest.TestCase):
    def test_cli_layer12_report_writes_chinese_report_and_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collection_path = root / "collection.json"
            analysis_path = root / "analysis.json"
            report_path = root / "report.md"
            validation_path = root / "validation.json"

            result = CollectionResult(
                collection_summary=CollectionSummary(
                    symbol="TSLA",
                    company_name="Tesla, Inc.",
                    overall_quality="MEDIUM",
                    can_generate_analysis=True,
                    confidence_cap="MEDIUM",
                    data_sources_used=["local", "rss"],
                ),
                market_data=[
                    PricePoint(
                        date_time=f"2026-06-{day:02d}",
                        close=100 + day,
                        high=102 + day,
                        low=98 + day,
                        volume=1000,
                        source="local",
                    )
                    for day in range(1, 22)
                ],
                news_events=[
                    NewsEvent(
                        title="Tesla AI chip team sets new target",
                        summary_raw="Tesla update.",
                        source="Reuters",
                        source_reliability=0.75,
                        related_symbols=["TSLA"],
                    )
                ],
                filings=[
                    FilingEvent(
                        filing_type="10-Q",
                        title="10-Q filing: Quarterly report",
                        source="SEC EDGAR",
                        source_reliability=1.0,
                    )
                ],
                macro_data=[
                    MacroPoint(
                        indicator_name="10Y Treasury Yield",
                        value=4.2,
                        date="2026-06-15",
                        source="FRED",
                        source_reliability=0.95,
                    )
                ],
                source_inventory=[
                    SourceRecord(name="rss", used=True, records_collected=1, raw_metadata={"symbols": ["TSLA"], "generated_feed_count": 1}),
                ],
                data_quality_report=DataQualityReport(overall_quality="MEDIUM", can_generate_analysis=True, confidence_cap="MEDIUM"),
            )
            collection_path.write_text(result.to_json(), encoding="utf-8")

            exit_code = main(
                [
                    "layer12-report",
                    "--collection-input",
                    str(collection_path),
                    "--analysis-output",
                    str(analysis_path),
                    "--report-output",
                    str(report_path),
                    "--validation-output",
                    str(validation_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(analysis_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(validation_path.exists())

            report = report_path.read_text(encoding="utf-8")
            self.assertIn("# TSLA 一二层测试中文报告", report)
            self.assertIn("## 测试结论", report)
            self.assertIn("## 合规边界检查", report)
            self.assertIn("不构成投资建议", report)

            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            serialized = json.dumps(analysis, ensure_ascii=False)
            self.assertNotIn("buy_signal", serialized)
            self.assertNotIn("sell_signal", serialized)
            self.assertNotIn("trade_plan", serialized)
            self.assertNotIn("generated_target_price", serialized)

            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertEqual(validation["blocking_failures"], [])


if __name__ == "__main__":
    unittest.main()
