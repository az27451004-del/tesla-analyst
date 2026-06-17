"""Markdown rendering for third-layer conditional decision plans."""

from __future__ import annotations

from typing import Any


def build_decision_markdown(plan: Any, *, symbol: str = "", analysis_generated_at: str = "") -> str:
    """Render a DecisionPlan without requiring the TSLA report pipeline."""
    lines: list[str] = []
    title_symbol = f"{symbol.upper()} " if symbol else ""
    lines.append(f"# {title_symbol}第三层条件化计划")
    lines.append("")
    if analysis_generated_at:
        lines.append(f"- 分析生成时间：{analysis_generated_at}")
    lines.append("- 用途：研究辅助；以下内容是条件化计划，不构成无条件投资建议。")
    lines.append("")

    lines.append("## 当前投资人画像")
    lines.append(f"- 投资人类型：{plan.profile.label}")
    lines.append(f"- 投资周期：{plan.profile.horizon}")
    lines.append("- 核心关注因子：" + "、".join(plan.profile.focus_factors))
    lines.append(
        "- 当前权重配置："
        + "；".join(f"{driver} {weight:.0%}" for driver, weight in plan.profile.weights.items() if weight > 0)
    )
    lines.append(f"- 当前倾向：{plan.current_bias}")
    lines.append(f"- 第三层置信度：{plan.confidence_level}")
    lines.append(f"- 画像加权分：{plan.weighted_score:.2f}")
    lines.append(f"- 当前画像数据覆盖等级：{plan.profile_coverage.coverage_level}")
    lines.append(f"- 当前画像置信度上限：{plan.profile_coverage.confidence_cap}")
    lines.append("")

    _append_items(lines, "支持因素", plan.supporting_factors)
    _append_items(lines, "风险因素", plan.risk_factors)
    _append_items(
        lines,
        "当前画像关键数据缺口",
        [f"{gap.label}：{gap.message}" for gap in plan.profile_coverage.critical_gaps]
        or ["当前画像没有额外关键数据缺口。"],
    )
    _append_items(lines, "条件化参与方案", plan.conditional_entry_plan)
    _append_items(lines, "卖出/减仓条件", plan.exit_or_reduce_conditions)
    _append_items(lines, "止损/失效条件", plan.stop_or_invalidation_conditions)
    _append_items(lines, "不交易条件", plan.no_trade_conditions)
    _append_items(lines, "反方观点", plan.contrarian_view)
    _append_items(lines, "后续监控清单", plan.monitoring_checklist)

    return "\n".join(lines)


def _append_items(lines: list[str], title: str, items: Any) -> None:
    lines.append(f"## {title}")
    for item in items:
        lines.append(f"- {item}")
    lines.append("")
