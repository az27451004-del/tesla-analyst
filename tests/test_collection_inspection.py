import json
import tempfile
import unittest
from pathlib import Path

from stock_agent.cli import main
from stock_agent.collection.inspection import build_collection_audit_markdown


class CollectionInspectionTest(unittest.TestCase):
    def test_minimal_payload_generates_markdown(self):
        payload = {
            "collection_summary": {
                "symbol": "TSLA",
                "company_name": "Tesla, Inc.",
                "overall_quality": "HIGH",
                "can_generate_analysis": True,
                "confidence_cap": "HIGH",
                "freshness_status": "FRESH",
                "ibkr_status": {"enabled": False, "connected": False, "account_data_allowed": False},
            },
            "data_quality_report": {
                "overall_quality": "HIGH",
                "can_generate_analysis": True,
                "confidence_cap": "HIGH",
                "missing_requirements": [],
                "warnings": [],
                "checks": {"conflict_count": 0},
            },
            "market_data": [],
            "filings": [],
            "macro_data": [],
            "news_events": [],
            "source_inventory": [],
            "warnings": [],
            "conflicts": [],
            "broker_account_data": [],
        }

        markdown = build_collection_audit_markdown(payload)

        self.assertIn("# 采集结果审计报告：TSLA", markdown)
        self.assertIn("总体质量：高 (HIGH)", markdown)
        self.assertIn("| 行情数据 | 0 |", markdown)
        self.assertIn("IBKR 是否启用：否", markdown)
        self.assertIn("券商账户数据：未采集到数据", markdown)

    def test_report_includes_sources_warnings_and_conflicts(self):
        payload = {
            "collection_summary": {
                "symbol": "TSLA",
                "ibkr_status": {"enabled": False},
            },
            "data_quality_report": {
                "overall_quality": "LOW",
                "can_generate_analysis": False,
                "confidence_cap": "LOW",
                "missing_requirements": ["market_data"],
                "warnings": ["missing market data"],
                "checks": {"conflict_count": 1, "duplicate_event_count": 2},
            },
            "source_inventory": [
                {
                    "name": "alpha_vantage",
                    "enabled": True,
                    "used": False,
                    "failed": True,
                    "reliability": 0.9,
                    "records_collected": 0,
                    "failure_reason": "rate limit",
                }
            ],
            "warnings": [{"severity": "ERROR", "source": "quality", "code": "missing_market_data", "message": "missing"}],
            "conflicts": [
                {
                    "conflict_type": "price",
                    "conflicting_sources": ["a", "b"],
                    "preferred_value": 1,
                    "requires_review": True,
                    "reason": "different values",
                }
            ],
            "market_data": [],
            "filings": [],
            "macro_data": [],
            "news_events": [],
            "broker_account_data": [],
        }

        markdown = build_collection_audit_markdown(payload)

        self.assertIn("alpha_vantage", markdown)
        self.assertIn("rate limit", markdown)
        self.assertIn("missing_market_data", markdown)
        self.assertIn("different values", markdown)
        lowered = markdown.lower()
        for forbidden in ("buy_signal", "sell_signal", "target_price recommendation", "trade_plan"):
            self.assertNotIn(forbidden, lowered)

    def test_cli_inspect_writes_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "collection.json"
            output_path = Path(temp_dir) / "audit.md"
            input_path.write_text(
                json.dumps(
                    {
                        "collection_summary": {"symbol": "TSLA", "ibkr_status": {"enabled": False}},
                        "data_quality_report": {"overall_quality": "HIGH", "checks": {}},
                        "market_data": [],
                        "filings": [],
                        "macro_data": [],
                        "news_events": [],
                        "source_inventory": [],
                        "warnings": [],
                        "conflicts": [],
                        "broker_account_data": [],
                    }
                ),
                encoding="utf-8",
            )

            exit_code = main(["inspect", "--input", str(input_path), "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            self.assertIn("采集结果审计报告", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
