import tempfile
import unittest
from pathlib import Path

from tsla_agent.cli import main


class CLIDecisionPlanTest(unittest.TestCase):
    def test_default_report_excludes_decision_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.md"

            exit_code = main(["--sample-data", "--offline", "--output", str(output)])

            self.assertEqual(exit_code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("## 数据源路线图与质量门禁", text)
            self.assertNotIn("## 交易/投资计划", text)
            self.assertNotIn("## 当前投资人画像", text)

    def test_explicit_flag_includes_short_term_decision_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.md"

            exit_code = main(
                [
                    "--sample-data",
                    "--offline",
                    "--include-decision-plan",
                    "--investor-type",
                    "short_term_trader",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(exit_code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("## 当前投资人画像", text)
            self.assertIn("短线交易者", text)
            self.assertIn("## 交易/投资计划", text)
            self.assertIn("### 当前画像关键数据缺口", text)
            self.assertIn("### 不交易条件", text)


if __name__ == "__main__":
    unittest.main()
