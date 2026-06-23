import json
import tempfile
import unittest
from pathlib import Path

from stock_agent.analysis import analyze_market_events
from stock_agent.cli import main as stock_agent_main
from stock_agent.decision.cli import main as decision_main
from tsla_agent.models import Event, PricePoint


def _write_analysis_json(path: Path) -> None:
    prices = [
        PricePoint(date=f"2026-06-{day:02d}", close=100 + day, high=102 + day, low=98 + day, volume=1000 + day)
        for day in range(1, 31)
    ]
    events = [
        Event(source="Reuters", title="Tesla deliveries beat consensus with record growth"),
        Event(source="SEC", title="Tesla faces regulatory investigation and recall"),
        Event(source="Reuters", title="Trump tariff policy pressures China trade talks and U.S. capital flows"),
    ]
    analysis = analyze_market_events(
        symbol="TSLA",
        prices=prices,
        events=events,
        missing_requirements=["macro_data", "financial_metrics", "options_data"],
    )
    path.write_text(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _write_collection_json(path: Path) -> None:
    payload = {
        "collection_summary": {
            "symbol": "TSLA",
            "company_name": "Tesla, Inc.",
            "collection_time": "2026-06-17T00:00:00+00:00",
        },
        "data_quality_report": {"overall_quality": "MEDIUM", "can_generate_analysis": True, "confidence_cap": "MEDIUM"},
        "source_inventory": [
            {"name": "rss", "raw_metadata": {"generated_feed_count": 3, "symbols": ["TSLA"]}},
        ],
        "market_data": [{"date": f"2026-06-{day:02d}", "close": 100 + day} for day in range(1, 31)],
        "news_events": [{"title": "Tesla faces regulatory investigation and recall"}],
        "filings": [{"title": "季度财报（10-Q）：Tesla, Inc. 最新披露"}],
        "macro_data": [{"series_id": "DGS10", "date": "2026-06-17", "value": 4.2}],
        "warnings": [],
        "conflicts": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class DecisionCLITest(unittest.TestCase):
    def test_standalone_decision_cli_outputs_json_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "analysis.json"
            output_path = Path(temp_dir) / "decision.json"
            _write_analysis_json(input_path)

            exit_code = decision_main(
                [
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--format",
                    "json",
                    "--investor-type",
                    "short_term_trader",
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            raw = json.dumps(payload, ensure_ascii=False)
            self.assertEqual(payload["profile"]["investor_type"], "short_term_trader")
            self.assertIn("conditional_entry_plan", payload)
            self.assertIn("no_trade_conditions", payload)
            self.assertNotIn("buy_signal", raw)
            self.assertNotIn("sell_signal", raw)

    def test_standalone_decision_cli_outputs_markdown_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "analysis.json"
            output_path = Path(temp_dir) / "decision.md"
            _write_analysis_json(input_path)

            exit_code = decision_main(
                [
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--format",
                    "markdown",
                    "--investor-type",
                    "long_term_fundamental",
                ]
            )

            self.assertEqual(exit_code, 0)
            text = output_path.read_text(encoding="utf-8")
            self.assertIn("# TSLA 第三层条件化计划", text)
            self.assertIn("## 条件化参与方案", text)
            self.assertIn("## 止损/失效条件", text)
            self.assertIn("## 不交易条件", text)
            self.assertIn("总得分", text)
            self.assertIn("## 得分含义说明", text)
            self.assertIn("> 0.18", text)
            self.assertIn("-0.18 到 0.18", text)
            self.assertIn("< -0.18", text)
            self.assertIn("LOW 置信度", text)
            self.assertIn("## 因子权重与贡献", text)
            self.assertIn("| 因子 | 画像权重 | 当前得分 | 加权贡献 |", text)
            self.assertIn("毛利率/EPS/现金流", text)
            self.assertIn("FSD/Robotaxi/AI", text)
            self.assertIn("25%", text)
            self.assertIn("12%", text)
            self.assertIn("当前无可评分证据", text)
            self.assertIn("反方观点", text)

    def test_stock_agent_cli_decide_uses_analysis_json_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "analysis.json"
            output_path = Path(temp_dir) / "decision.json"
            _write_analysis_json(input_path)

            exit_code = stock_agent_main(
                [
                    "decide",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--format",
                    "json",
                    "--investor-type",
                    "risk_control",
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["profile"]["investor_type"], "risk_control")
            self.assertTrue(payload["contrarian_view"])

    def test_stock_agent_cli_layer123_report_outputs_all_profiles_and_chinese_titles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collection_path = root / "collection.json"
            analysis_path = root / "analysis.json"
            report_path = root / "layer123.md"
            validation_path = root / "validation.json"
            _write_collection_json(collection_path)
            _write_analysis_json(analysis_path)

            exit_code = stock_agent_main(
                [
                    "layer123-report",
                    "--collection-input",
                    str(collection_path),
                    "--analysis-input",
                    str(analysis_path),
                    "--output-dir",
                    str(root),
                    "--report-output",
                    str(report_path),
                    "--validation-output",
                    str(validation_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            report = report_path.read_text(encoding="utf-8")
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertIn("# TSLA 一二三层测试中文报告", report)
            self.assertIn("## 六类画像结果对比", report)
            self.assertIn("## 重要资讯中文摘要", report)
            self.assertIn("中文标题 / 原题译文", report)
            self.assertIn("事件层级", report)
            self.assertIn("解释框架", report)
            self.assertIn("美国地缘经济优先", report)
            self.assertIn("发布时间", report)
            self.assertIn("特斯拉面临监管调查和召回风险", report)
            self.assertIn("影响分含义说明", report)
            self.assertIn("0.70 以上", report)
            self.assertIn("0.50-0.70", report)
            self.assertIn("影响等级", report)
            self.assertIn("中高影响事件", report)
            self.assertIn("具体影响分", report)
            self.assertIn("### 事件影响分解释", report)
            self.assertIn("方向理由", report)
            self.assertIn("量化证据", report)
            self.assertIn("影响分计算", report)
            self.assertIn("反方论点", report)
            self.assertIn("## 得分含义说明", report)
            self.assertIn("> 0.18", report)
            self.assertIn("-0.18 到 0.18", report)
            self.assertIn("< -0.18", report)
            self.assertIn("LOW 置信度", report)
            self.assertIn("总得分", report)
            self.assertIn("| 因子 | 画像权重 | 当前得分 | 加权贡献 |", report)
            self.assertIn("毛利率/EPS/现金流", report)
            self.assertIn("FSD/Robotaxi/AI", report)
            self.assertIn("25%", report)
            self.assertIn("12%", report)
            self.assertIn("贡献合计", report)
            self.assertIn("当前无可评分证据", report)
            self.assertIn("监管调查或召回风险", report)
            self.assertIn("英文原题：Tesla faces regulatory investigation and recall", report)
            self.assertIn("事件#", report)
            for bad_punctuation in ("。、", "，、", "、、", "。。"):
                self.assertNotIn(bad_punctuation, report)
            self.assertEqual(validation["status"], "通过，带降级观察")
            for profile in (
                "long_term_fundamental",
                "growth_narrative",
                "event_driven",
                "swing_trader",
                "short_term_trader",
                "risk_control",
            ):
                self.assertTrue((root / f"decision_plan_{profile}_tsla_live.json").exists())
                self.assertTrue((root / f"decision_plan_{profile}_tsla_live.md").exists())
            raw = ""
            for profile in (
                "long_term_fundamental",
                "growth_narrative",
                "event_driven",
                "swing_trader",
                "short_term_trader",
                "risk_control",
            ):
                raw += (root / f"decision_plan_{profile}_tsla_live.json").read_text(encoding="utf-8")
                raw += (root / f"decision_plan_{profile}_tsla_live.md").read_text(encoding="utf-8")
            self.assertNotIn("buy_signal", raw)
            self.assertNotIn("sell_signal", raw)
            self.assertNotIn("trade_plan", raw)
            self.assertNotIn("generated_target_price", raw)


if __name__ == "__main__":
    unittest.main()
