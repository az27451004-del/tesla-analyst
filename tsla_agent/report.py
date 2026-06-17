from __future__ import annotations

from pathlib import Path
from typing import Any

from tsla_agent.models import ForecastResult, MarketSummary, now_iso


def build_markdown_report(
    market: MarketSummary,
    events,
    forecast: ForecastResult,
    warnings: list[str],
    llm_summary: str | None = None,
    *,
    analysis: Any | None = None,
    decision_plan: Any | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# {market.symbol} 股价分析报告")
    lines.append("")
    lines.append(f"- 生成时间：{now_iso()}")
    if decision_plan:
        lines.append("- 用途：研究辅助；包含按投资者画像生成的条件化计划，不构成无条件投资建议。")
    else:
        lines.append("- 用途：研究辅助，不构成投资建议。")
    lines.append("")

    lines.append("## 数据状态")
    if analysis:
        lines.append(f"- 分析置信度：{analysis.confidence_level}")
        lines.append(f"- 数据覆盖等级：{analysis.data_coverage.coverage_level}")
        lines.append(f"- 数据覆盖置信度上限：{analysis.data_coverage.confidence_cap}")
        lines.append(f"- 数据质量降级项：{len(analysis.quality_downgrades)}")
        if analysis.quality_downgrades:
            for item in analysis.quality_downgrades[:5]:
                lines.append(f"  - {item}")
        else:
            lines.append("- 数据质量降级项：无")
    else:
        lines.append("- 分析置信度：未生成通用分析结果")
    lines.append("")

    if analysis:
        lines.append("## 数据源路线图与质量门禁")
        if analysis.data_coverage.gaps:
            lines.append("### 当前关键数据缺口")
            for gap in analysis.data_coverage.gaps[:6]:
                sources = "、".join(gap.recommended_sources[:3])
                lines.append(
                    f"- {gap.label}（{gap.severity}，置信度上限 {gap.confidence_cap}）："
                    f"{gap.message} 建议低成本来源：{sources}。"
                )
        else:
            lines.append("- 当前数据覆盖未触发结构化缺口。")
        lines.append("")
        lines.append("### 路线图优先级")
        for item in analysis.data_coverage.roadmap:
            lines.append(f"- {item.priority}｜{item.label}：{item.current_status}")
        lines.append("")

    if decision_plan:
        lines.append("## 当前投资人画像")
        lines.append(f"- 投资人类型：{decision_plan.profile.label}")
        lines.append(f"- 投资周期：{decision_plan.profile.horizon}")
        lines.append("- 核心关注因子：" + "、".join(decision_plan.profile.focus_factors))
        lines.append("- 当前权重配置：" + "；".join(
            f"{driver} {weight:.0%}" for driver, weight in decision_plan.profile.weights.items() if weight > 0
        ))
        lines.append(f"- 当前画像数据覆盖等级：{decision_plan.profile_coverage.coverage_level}")
        lines.append(f"- 当前画像置信度上限：{decision_plan.profile_coverage.confidence_cap}")
        lines.append("")

    lines.append("## 核心结论")
    if llm_summary:
        lines.append(llm_summary)
    elif decision_plan:
        lines.append(
            f"{market.symbol} 当前对“{decision_plan.profile.label}”的表达为“{decision_plan.current_bias}”，"
            f"第三层计划置信度为 {decision_plan.confidence_level}，画像加权分为 {decision_plan.weighted_score:.2f}。"
            "该结论必须结合触发条件、止损/失效条件和不交易条件使用。"
        )
    else:
        lines.append(_fallback_summary(market, events, forecast))
    lines.append("")

    lines.append("## 市场状态")
    lines.append(f"- 最新收盘价：{_fmt_price(market.last_close)}")
    lines.append(f"- 最新日期：{market.last_date or '无'}")
    lines.append(f"- 5 日涨跌幅：{_fmt_pct(market.change_5d_pct)}")
    lines.append(f"- 20 日涨跌幅：{_fmt_pct(market.change_20d_pct)}")
    lines.append(f"- 年化波动率：{_fmt_pct(market.annualized_volatility_pct)}")
    lines.append(f"- 20 日均线：{_fmt_price(market.sma_20)}")
    lines.append(f"- 50 日均线：{_fmt_price(market.sma_50)}")
    lines.append(f"- 趋势判断：{market.trend_label}")
    lines.append("")

    lines.append("## 关键事件分析")
    if events:
        for event in events[:10]:
            sentiment = "正面" if event.sentiment > 0.15 else "负面" if event.sentiment < -0.15 else "中性"
            source = f" [{event.source}]" if event.source else ""
            url = f" ({event.url})" if event.url else ""
            lines.append(
                f"- {event.title}{source}：类别 {event.category}，情绪 {sentiment}，影响分 {event.impact_score:.2f}。{event.summary[:220]}{url}"
            )
    else:
        lines.append("- 暂无事件数据。")
    lines.append("")

    if analysis:
        lines.append("## 驱动因子权重分析")
        for driver, score in analysis.driver_scores.items():
            lines.append(f"- {driver}：{score:.2f}")
        lines.append("")

    lines.append("## 情景预测")
    lines.append(f"- 信号：{forecast.signal}")
    lines.append(f"- 依据：{forecast.rationale}")
    if forecast.points:
        lines.append("")
        lines.append("| 周期 | 基准价 | 乐观情景 | 悲观情景 | 基准收益 | 置信带 |")
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for point in forecast.points:
            lines.append(
                f"| {point.horizon_days} 日 | ${point.base_price:.2f} | ${point.bull_price:.2f} | "
                f"${point.bear_price:.2f} | {point.expected_return_pct:.2f}% | ±{point.confidence_band_pct:.2f}% |"
            )
    lines.append("")

    if analysis and analysis.scenario_forecasts:
        lines.append("### 通用 Bear/Base/Bull 情景")
        for scenario in analysis.scenario_forecasts:
            low = _fmt_price(scenario.price_low)
            high = _fmt_price(scenario.price_high)
            lines.append(f"- {scenario.name}（{scenario.horizon}）：{low} - {high}。{scenario.rationale}")
        lines.append("")

    if decision_plan:
        lines.append("## 交易/投资计划")
        lines.append("### 支持因素")
        for item in decision_plan.supporting_factors:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### 风险因素")
        for item in decision_plan.risk_factors:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### 当前画像关键数据缺口")
        for gap in decision_plan.profile_coverage.critical_gaps[:5]:
            lines.append(f"- {gap.label}：{gap.message}")
        if not decision_plan.profile_coverage.critical_gaps:
            lines.append("- 当前画像没有额外关键数据缺口。")
        lines.append("")
        lines.append("### 条件化参与方案")
        for item in decision_plan.conditional_entry_plan:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### 卖出/减仓条件")
        for item in decision_plan.exit_or_reduce_conditions:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### 止损/失效条件")
        for item in decision_plan.stop_or_invalidation_conditions:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### 不交易条件")
        for item in decision_plan.no_trade_conditions:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 反方观点")
    if decision_plan:
        for item in decision_plan.contrarian_view:
            lines.append(f"- {item}")
    else:
        lines.append("- 正面事件可能已被价格提前反映，需要后续数据验证。")
        lines.append("- 若宏观利率、监管、竞争或成交量结构恶化，当前分析信号可能失效。")
        lines.append("- 关键证伪数据包括交付量、库存、毛利率、成交量、支撑/压力表现和官方披露。")
    lines.append("")

    lines.append("## 后续监控清单")
    if decision_plan:
        for item in decision_plan.monitoring_checklist:
            lines.append(f"- {item}")
    else:
        lines.append("- 最新价格、成交量、主要支撑/压力和波动率。")
        lines.append("- 交付量、库存、价格调整和毛利率变化。")
        lines.append("- 自动驾驶/Robotaxi、监管调查、召回、诉讼和安全事件。")
        lines.append("- 利率、美元、风险偏好、纳指走势和高估值成长股流动性。")
        lines.append("- 竞争格局，尤其是中国和欧洲 EV 市场份额。")
        lines.append("- 财报指引、资本开支、自由现金流和管理层表态。")
    lines.append("")

    if warnings:
        lines.append("## 数据覆盖提醒")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## 方法说明")
    lines.append(
        "该 MVP 使用三层架构：第一层收集事实，第二层生成分析信号，第三层在显式开启时生成条件化计划。"
        "生产环境必须加入更完整的数据源、回测、漂移监控和人工复核。"
    )
    lines.append("")
    return "\n".join(lines)


def write_report(content: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _fallback_summary(market: MarketSummary, events, forecast: ForecastResult) -> str:
    top = events[0].title if events else "暂无高置信事件"
    return (
        f"{market.symbol} 当前趋势为“{market.trend_label}”，模型短期信号为“{forecast.signal}”。"
        f"最重要的已收集事件是：{top}。该结论依赖当前数据覆盖，若缺少实时新闻、期权、宏观和盘中行情，"
        "需要降低置信度。"
    )


def _fmt_price(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "无"


def _fmt_pct(value: float | None) -> str:
    return f"{value:.2f}%" if value is not None else "无"
