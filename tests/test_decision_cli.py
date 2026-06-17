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
    ]
    analysis = analyze_market_events(
        symbol="TSLA",
        prices=prices,
        events=events,
        missing_requirements=["macro_data", "financial_metrics", "options_data"],
    )
    path.write_text(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()
