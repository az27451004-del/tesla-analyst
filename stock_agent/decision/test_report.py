"""Run third-layer tests and generate a Chinese Markdown report."""

from __future__ import annotations

import argparse
import contextlib
import io
import platform
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_TEST_MODULES = (
    "tests.test_decision",
    "tests.test_decision_cli",
    "tests.test_cli_decision_plan",
)

DEFAULT_OUTPUT = Path("reports/decision_layer_test_report.md")

TEST_COVERAGE = (
    "第三层核心逻辑：不同投资者画像、画像权重、置信度门禁、反方观点和失效条件。",
    "第三层独立运行：从 AnalysisResult JSON 生成 DecisionPlan JSON/Markdown。",
    "TSLA 报告接入：默认不展示第三层，显式开启后才展示交易/投资计划。",
    "边界约束：第三层输出不包含无条件 buy_signal 或 sell_signal 字段。",
)

KNOWN_RISKS = (
    "未知 investor_type 当前会静默回退到 long_term_fundamental，可能掩盖输入拼写错误。",
    "坏 JSON 输入的失败路径已有基础保护，但还可以继续补更多字段级异常测试。",
    "当前报告聚焦第三层相关测试，不替代 python3 -m unittest discover 的全仓库回归。",
)

NEXT_TEST_ITEMS = (
    "补充 6 个画像的完整字段存在性测试，确保每个画像都输出支持因素、风险因素、条件化参与、退出、失效、不交易、反方观点和监控清单。",
    "补充第一层 CollectionResult JSON 误传给第三层 CLI 时的失败提示测试。",
    "补充 unknown investor_type 的行为测试，明确是继续回退还是改为报错。",
)


@dataclass(frozen=True)
class DecisionLayerTestReport:
    exit_code: int
    output_path: Path
    content: str
    tests_run: int
    failures: int
    errors: int


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_decision_layer_test_report(
        output_path=Path(args.output),
        verbosity=args.verbosity,
        test_modules=DEFAULT_TEST_MODULES,
        command_args=["python3", "-m", "stock_agent.decision.test_report", "--output", args.output],
    )
    print(f"第三层测试报告已生成：{report.output_path}")
    print(f"测试结论：{'通过' if report.exit_code == 0 else '未通过'}")
    return report.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run third-layer tests and generate a Chinese Markdown report")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown report output path")
    parser.add_argument("--verbosity", type=int, choices=(1, 2), default=1, help="unittest verbosity")
    return parser


def run_decision_layer_test_report(
    *,
    output_path: Path,
    verbosity: int = 1,
    test_modules: Iterable[str] = DEFAULT_TEST_MODULES,
    command_args: Iterable[str] = (),
) -> DecisionLayerTestReport:
    modules = tuple(test_modules)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    runner = unittest.TextTestRunner(stream=stream, verbosity=verbosity)

    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        result = runner.run(suite)

    content = build_report_markdown(
        result=result,
        runner_output=stream.getvalue(),
        test_modules=modules,
        command_args=tuple(command_args),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    exit_code = 0 if result.wasSuccessful() else 1
    return DecisionLayerTestReport(
        exit_code=exit_code,
        output_path=output_path,
        content=content,
        tests_run=result.testsRun,
        failures=len(result.failures),
        errors=len(result.errors),
    )


def build_report_markdown(
    *,
    result: unittest.TestResult,
    runner_output: str,
    test_modules: tuple[str, ...],
    command_args: tuple[str, ...],
) -> str:
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(getattr(result, "skipped", ()))
    passed = result.testsRun - failures - errors - skipped
    successful = result.wasSuccessful()
    generated_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    command = " ".join(command_args) if command_args else "python3 -m stock_agent.decision.test_report"

    lines: list[str] = [
        "# 第三层测试报告",
        "",
        "## 结论",
    ]
    if successful:
        lines.append("- 结论：第三层相关测试全部通过，当前未发现阻断性问题。")
        lines.append("- 阻断问题判断：未发现会阻止第三层独立运行或报告接入的阻断问题。")
    else:
        lines.append("- 结论：第三层测试未通过，存在需要修复的问题，详见失败详情。")
        lines.append("- 阻断问题判断：发现失败或错误，修复前不建议把本次第三层结果用于正式判断。")
    lines.extend(
        [
            "",
            "## 运行信息",
            f"- 测试时间：{generated_at}",
            f"- 测试命令：`{command}`",
            f"- Python：{platform.python_version()}",
            f"- 系统：{platform.platform()}",
            f"- 工作目录：`{Path.cwd()}`",
            "",
            "## 测试范围",
        ]
    )
    for module in test_modules:
        lines.append(f"- `{module}`")
    lines.append("")
    for item in TEST_COVERAGE:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 测试结果",
            f"- 总测试数：{result.testsRun}",
            f"- 通过数量：{passed}",
            f"- 失败数量：{failures}",
            f"- 错误数量：{errors}",
            f"- 跳过数量：{skipped}",
            "",
            "## 失败与错误详情",
        ]
    )
    if failures or errors:
        for test, traceback_text in result.failures:
            lines.append(f"### 失败：`{test.id()}`")
            lines.append("```text")
            lines.append(traceback_text.rstrip())
            lines.append("```")
        for test, traceback_text in result.errors:
            lines.append(f"### 错误：`{test.id()}`")
            lines.append("```text")
            lines.append(traceback_text.rstrip())
            lines.append("```")
    else:
        lines.append("- 无。")

    lines.extend(["", "## 已知风险与建议"])
    for item in KNOWN_RISKS:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 建议下一步测试项")
    for item in NEXT_TEST_ITEMS:
        lines.append(f"- {item}")

    lines.extend(["", "## 原始 unittest 输出", "```text", runner_output.rstrip() or "无输出", "```", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
