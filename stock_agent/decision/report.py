"""Markdown rendering for third-layer conditional decision plans."""

from __future__ import annotations

from typing import Any


def build_decision_markdown(
    plan: Any,
    *,
    symbol: str = "",
    analysis_generated_at: str = "",
    driver_scores: dict[str, float] | None = None,
) -> str:
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
    lines.append(f"- 总得分：{plan.weighted_score:.3f}")
    lines.append("- 计算方式：总得分 = Σ(因子权重 x 当前因子得分)，因子得分范围约为 -1 到 1，权重合计约为 100%。")
    lines.append(f"- 当前解读：{_score_interpretation(plan.current_bias)}")
    lines.append(f"- 当前画像数据覆盖等级：{plan.profile_coverage.coverage_level}")
    lines.append(f"- 当前画像置信度上限：{plan.profile_coverage.confidence_cap}")
    lines.append("")

    _append_score_meaning(lines)
    _append_factor_contribution_table(lines, plan, driver_scores)
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


def _append_score_meaning(lines: list[str]) -> None:
    lines.append("## 得分含义说明")
    lines.append("- `> 0.18`：条件偏多，说明当前证据整体偏正，但仍需满足触发条件。")
    lines.append("- `-0.18 到 0.18`：区间观察，说明多空证据不够悬殊，优先等待确认。")
    lines.append("- `< -0.18`：条件偏谨慎，说明风险或负面证据占优。")
    lines.append("- `LOW 置信度`：低置信度观察，数据质量或覆盖不足时不应把分数当作强信号。")
    lines.append("")


def _append_factor_contribution_table(lines: list[str], plan: Any, driver_scores: dict[str, float] | None) -> None:
    lines.append("## 因子权重与贡献")
    lines.append("| 因子 | 画像权重 | 当前得分 | 加权贡献 |")
    lines.append("|---|---:|---:|---:|")
    scores = driver_scores or {}
    for driver, weight in sorted(plan.profile.weights.items(), key=lambda item: item[1], reverse=True):
        if weight <= 0:
            continue
        score = scores.get(driver)
        contribution = None if score is None else weight * float(score)
        lines.append(
            f"| {driver} | {weight:.0%} | {_fmt_factor_score(score)} | {_fmt_optional(contribution, 3)} |"
        )
    lines.append(f"- 贡献合计：{plan.weighted_score:.3f}")
    lines.append("")


def _append_items(lines: list[str], title: str, items: Any) -> None:
    lines.append(f"## {title}")
    for item in items:
        lines.append(f"- {item}")
    lines.append("")


def _score_interpretation(current_bias: str) -> str:
    if current_bias == "低置信度观察":
        return "低置信度观察，数据质量或覆盖不足时不应把分数当作强信号。"
    if current_bias == "条件偏多":
        return "条件偏多，当前证据整体偏正，但仍需满足触发条件。"
    if current_bias == "条件偏谨慎":
        return "条件偏谨慎，风险或负面证据占优。"
    return "区间观察，多空证据不够悬殊，优先等待确认。"


def _fmt_optional(value: Any, digits: int) -> str:
    if value is None or value == "":
        return "无"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_factor_score(value: Any) -> str:
    if value is None or value == "":
        return "无"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{numeric:.3f}"
    if abs(numeric) < 0.0005:
        return f"{text}（当前无可评分证据）"
    return text
