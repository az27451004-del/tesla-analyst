import sys
import tempfile
import unittest
from pathlib import Path

from stock_agent.decision.test_report import main, run_decision_layer_test_report


class DecisionTestReportTest(unittest.TestCase):
    def test_report_runner_generates_required_chinese_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "decision_layer_test_report.md"

            report = run_decision_layer_test_report(
                output_path=output,
                verbosity=1,
                command_args=("python3", "-m", "stock_agent.decision.test_report", "--output", str(output)),
            )

            self.assertEqual(report.exit_code, 0)
            self.assertGreater(report.tests_run, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("# 第三层测试报告", text)
            self.assertIn("## 结论", text)
            self.assertIn("第三层相关测试全部通过", text)
            self.assertIn("当前未发现阻断性问题", text)
            self.assertIn("## 测试范围", text)
            self.assertIn("## 测试结果", text)
            self.assertIn("## 失败与错误详情", text)
            self.assertIn("## 已知风险与建议", text)
            self.assertIn("tests.test_decision", text)
            self.assertIn("失败数量：0", text)
            self.assertIn("错误数量：0", text)

    def test_cli_main_supports_custom_output_and_verbosity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "custom_report.md"

            exit_code = main(["--output", str(output), "--verbosity", "2"])

            self.assertEqual(exit_code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("# 第三层测试报告", text)
            self.assertIn("测试命令：", text)
            self.assertIn("tests.test_decision_cli", text)

    def test_failure_report_is_written_and_returns_exit_code_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            module_path = temp_path / "failing_decision_report_module.py"
            output = temp_path / "failure_report.md"
            module_path.write_text(
                "import unittest\n\n"
                "class FailingDecisionReportTest(unittest.TestCase):\n"
                "    def test_failure(self):\n"
                "        self.fail('intentional failure for report verification')\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(temp_path))
            try:
                report = run_decision_layer_test_report(
                    output_path=output,
                    test_modules=("failing_decision_report_module",),
                    command_args=("python3", "-m", "stock_agent.decision.test_report"),
                )
            finally:
                sys.path.remove(str(temp_path))
                sys.modules.pop("failing_decision_report_module", None)

            self.assertEqual(report.exit_code, 1)
            self.assertEqual(report.failures, 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("第三层测试未通过", text)
            self.assertIn("失败数量：1", text)
            self.assertIn("intentional failure for report verification", text)


if __name__ == "__main__":
    unittest.main()
