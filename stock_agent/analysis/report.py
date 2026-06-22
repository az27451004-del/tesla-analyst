"""Chinese reporting helpers for first-to-second-layer validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stock_agent.reporting.text import join_readable_items
from stock_agent.reporting.pdf import write_pdf_for_markdown

from .chinese_titles import event_title_with_translation
from .pipeline import analyze_collection


FORBIDDEN_DECISION_FIELDS = ("buy_signal", "sell_signal", "trade_plan", "generated_target_price")
CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def write_layer12_test_outputs(
    *,
    collection_input: Path,
    analysis_output: Path,
    report_output: Path,
    validation_output: Path | None = None,
) -> dict[str, Any]:
    """Analyze a CollectionResult JSON file and write Chinese validation artifacts."""
    collection = json.loads(collection_input.read_text(encoding="utf-8"))
    analysis = analyze_collection(collection).to_dict()

    analysis_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    analysis_output.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    output_files = {
        "collection_json": str(collection_input),
        "analysis_json": str(analysis_output),
        "report_markdown": str(report_output),
    }
    if validation_output:
        output_files["validation_json"] = str(validation_output)

    report, validation = build_layer12_test_report(
        collection=collection,
        analysis=analysis,
        output_files=output_files,
    )
    report_output.write_text(report, encoding="utf-8")
    pdf_output = write_pdf_for_markdown(report_output)
    if pdf_output:
        output_files["report_pdf"] = str(pdf_output)
        validation["output_files"] = dict(output_files)

    if validation_output:
        validation_output.parent.mkdir(parents=True, exist_ok=True)
        validation_output.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    return validation


def build_layer12_test_report(
    *,
    collection: dict[str, Any],
    analysis: dict[str, Any],
    output_files: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    summary = _dict(collection.get("collection_summary"))
    quality = _dict(collection.get("data_quality_report"))
    checks = _dict(quality.get("checks"))
    warnings = _list(collection.get("warnings"))
    conflicts = _list(collection.get("conflicts"))
    source_inventory = _list(collection.get("source_inventory"))
    rss_sources = [source for source in source_inventory if _dict(source).get("name") == "rss"]
    rss_meta = _dict(_dict(rss_sources[-1]).get("raw_metadata")) if rss_sources else {}
    market = _dict(analysis.get("market_state"))
    coverage = _dict(analysis.get("data_coverage"))
    scenarios = _list(analysis.get("scenario_forecasts"))
    events = _list(analysis.get("event_signals"))

    collection_serialized = json.dumps(collection, ensure_ascii=False)
    analysis_serialized = json.dumps(analysis, ensure_ascii=False)

    layer1_checks = {
        "股票代码为 TSLA": summary.get("symbol") == "TSLA",
        "行情数据不少于 20 条": len(_list(collection.get("market_data"))) >= 20,
        "新闻事件大于 0 条": len(_list(collection.get("news_events"))) > 0,
        "SEC filings 大于 0 条": len(_list(collection.get("filings"))) > 0,
        "宏观数据大于 0 条": len(_list(collection.get("macro_data"))) > 0,
        "RSS 自动 feed 已生成": int(rss_meta.get("generated_feed_count") or 0) > 0 if rss_sources else True,
    }
    layer2_checks = {
        "分析结果股票代码为 TSLA": analysis.get("symbol") == "TSLA",
        "最新收盘价存在": market.get("last_close") is not None,
        "最新交易日期存在": bool(market.get("last_date")),
        "事件信号大于 0 条": len(events) > 0,
        "前三情景包含 Bear/Base/Bull": {"Bear Case", "Base Case", "Bull Case"}.issubset(
            {str(item.get("name")) for item in scenarios if isinstance(item, dict)}
        ),
        "数据覆盖上限约束最终置信度": _confidence_rank(analysis.get("confidence_level")) <= _confidence_rank(coverage.get("confidence_cap")),
        "事件信号字段完整": _event_signal_fields_complete(events),
    }
    compliance_checks = {f"一层不含 {name}": name not in collection_serialized for name in FORBIDDEN_DECISION_FIELDS}
    compliance_checks.update({f"二层不含 {name}": name not in analysis_serialized for name in FORBIDDEN_DECISION_FIELDS})
    all_checks = {**layer1_checks, **layer2_checks, **compliance_checks}
    blocking_failures = [name for name, ok in all_checks.items() if not ok]

    if blocking_failures:
        conclusion = "一二层测试已完成，但存在未通过检查项，需要复核后再作为稳定流程使用。"
        status = "未完全通过"
    elif warnings or analysis.get("quality_downgrades") or coverage.get("gaps"):
        conclusion = "一二层测试跑通，未发现阻断问题；存在数据覆盖或质量降级项，分析置信度需按报告降级理解。"
        status = "通过，带降级观察"
    else:
        conclusion = "一二层测试跑通，核心采集、分析和合规边界检查均通过。"
        status = "通过"

    validation = {
        "status": status,
        "blocking_failures": blocking_failures,
        "layer1_checks": layer1_checks,
        "layer2_checks": layer2_checks,
        "compliance_checks": compliance_checks,
        "output_files": dict(output_files or {}),
    }

    lines: list[str] = []
    lines.append("# TSLA 一二层测试中文报告")
    lines.append("")
    lines.append("## 测试结论")
    lines.append(f"- 结论：{conclusion}")
    lines.append(f"- 测试状态：{status}")
    lines.append(f"- 生成时间：{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")
    lines.append("")

    lines.append("## 测试范围与声明")
    lines.append("- 测试对象：TSLA / Tesla, Inc.")
    lines.append("- 测试范围：第一层信息采集与第二层分析处理。")
    lines.append("- 未执行内容：未触发第三层决策表达层，未生成投资者画像计划。")
    lines.append("- 合规声明：本报告仅用于系统测试和研究辅助，不构成投资建议，不提供买卖判断、目标价推荐或交易计划。")
    lines.append("")

    lines.append("## 第一层采集结果")
    lines.append(f"- 股票代码：{_text(summary.get('symbol'))}")
    lines.append(f"- 公司名称：{_text(summary.get('company_name'))}")
    lines.append(f"- 采集时间：{_text(summary.get('collection_time'))}")
    lines.append(f"- 已使用数据源：{_join(summary.get('data_sources_used'))}")
    lines.append(f"- 失败数据源：{_join(summary.get('data_sources_failed'))}")
    lines.append(f"- Warning 数量：{len(warnings)}")
    lines.append(f"- 行情数据：{len(_list(collection.get('market_data')))} 条")
    lines.append(f"- 新闻事件：{len(_list(collection.get('news_events')))} 条")
    lines.append(f"- SEC filings：{len(_list(collection.get('filings')))} 条")
    lines.append(f"- 宏观数据：{len(_list(collection.get('macro_data')))} 条")
    lines.append(
        "- RSS 自动 symbol feed："
        f"生成 {rss_meta.get('generated_feed_count', 0)} 个，"
        f"静态 feed {rss_meta.get('static_feed_count', 0)} 个，"
        f"symbols={_join(rss_meta.get('symbols'))}"
    )
    lines.append("")

    lines.append("## 第一层质量门禁")
    lines.append(f"- 总体质量：{_text(quality.get('overall_quality') or summary.get('overall_quality'))}")
    lines.append(f"- 是否可进入后续分析：{'是' if quality.get('can_generate_analysis') or summary.get('can_generate_analysis') else '否'}")
    lines.append(f"- 置信度上限：{_text(quality.get('confidence_cap') or summary.get('confidence_cap'))}")
    lines.append(f"- 缺失需求：{_join(quality.get('missing_requirements'))}")
    lines.append(f"- 冲突数量：{len(conflicts)}")
    lines.append(f"- 合并重复事件数：{_text(checks.get('duplicate_event_count'), '0')}")
    lines.append(f"- 未知来源数量：{_text(checks.get('unknown_source_count'), '0')}")
    if warnings:
        lines.append("")
        lines.append("### 第一层 Warning 明细")
        lines.append("| 严重级别 | 来源 | 代码 | 信息 |")
        lines.append("|---|---|---|---|")
        for warning in warnings[:20]:
            item = _dict(warning)
            lines.append(f"| {_cell(item.get('severity'))} | {_cell(item.get('source'))} | {_cell(item.get('code'))} | {_cell(item.get('message'))} |")
    lines.append("")

    lines.append("## 第二层分析结果")
    lines.append(f"- 分析股票代码：{_text(analysis.get('symbol'))}")
    lines.append(f"- 分析置信度：{_text(analysis.get('confidence_level'))}")
    lines.append(f"- 数据覆盖等级：{_text(coverage.get('coverage_level'))}")
    lines.append(f"- 数据覆盖置信度上限：{_text(coverage.get('confidence_cap'))}")
    lines.append(f"- 最新收盘价：{_num(market.get('last_close'))}")
    lines.append(f"- 最新交易日期：{_text(market.get('last_date'))}")
    lines.append(f"- 5 日涨跌幅：{_num(market.get('change_5d_pct'))}%")
    lines.append(f"- 20 日涨跌幅：{_num(market.get('change_20d_pct'))}%")
    lines.append(f"- 年化波动率：{_num(market.get('annualized_volatility_pct'))}%")
    lines.append(f"- 20 日均线：{_num(market.get('sma_20'))}")
    lines.append(f"- 50 日均线：{_num(market.get('sma_50'))}")
    lines.append(f"- 支撑位：{_num(market.get('support_level'))}")
    lines.append(f"- 压力位：{_num(market.get('resistance_level'))}")
    lines.append(f"- ATR 14：{_num(market.get('atr_14'))}")
    lines.append(f"- 趋势标签：{_text(market.get('trend_label'))}")
    lines.append(f"- 事件信号数量：{len(events)}")
    lines.append("")

    _append_top_events(lines, events)
    _append_sec_summary(lines, _list(collection.get("filings")))
    _append_driver_scores(lines, _dict(analysis.get("driver_scores")))
    _append_scenarios(lines, scenarios)
    _append_validation(lines, layer1_checks, layer2_checks)
    _append_coverage_gaps(lines, _list(coverage.get("gaps")))
    _append_compliance(lines, compliance_checks)
    _append_observations(lines, blocking_failures, warnings, coverage, events)

    lines.append("## 输出文件")
    for label, key in (
        ("第一层采集 JSON", "collection_json"),
        ("第二层分析 JSON", "analysis_json"),
        ("一二层中文综合测试报告", "report_markdown"),
        ("校验结果 JSON", "validation_json"),
    ):
        if validation["output_files"].get(key):
            lines.append(f"- {label}：`{validation['output_files'][key]}`")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n", validation


def _append_top_events(lines: list[str], events: list[Any]) -> None:
    lines.append("### Top 10 事件信号")
    if not events:
        lines.append("- 未生成事件信号。")
        lines.append("")
        return
    _append_impact_score_meaning(lines, heading="#### 影响分含义说明")
    lines.append("| 排名 | 事件层级 | 发布时间 | 驱动因子 | 方向 | 影响等级 | 来源可信度 | 中文标题 / 原题译文 |")
    lines.append("|---:|---|---|---|---|---|---:|---|")
    for index, event in enumerate(events[:10], 1):
        item = _dict(event)
        title = _text(item.get("title"))
        lines.append(
            f"| {index} | {_cell(item.get('event_scope'))} | {_cell(_event_display_time(item))} | {_cell(item.get('driver'))} | {_cell(item.get('direction'))} | "
            f"{_cell(_impact_level(item.get('impact_score')))} | {_num(item.get('source_reliability'), 3)} | "
            f"{_cell(event_title_with_translation(title, item.get('driver')))} |"
        )
    lines.append("")
    lines.append("#### 事件影响分解释")
    for index, event in enumerate(events[:10], 1):
        item = _dict(event)
        title = _text(item.get("title"))
        lines.append(f"**{index}. {event_title_with_translation(title, item.get('driver'))}**")
        lines.append(f"- 事件层级：{_text(item.get('event_scope'), '公司级事件')}")
        lines.append(f"- 发布时间：{_text(_event_display_time(item), '未提供')}")
        lines.append(f"- 英文原题：{_text(title)}")
        lines.append(f"- 影响等级：{_impact_level(item.get('impact_score'))}；具体影响分：{_num(item.get('impact_score'), 3)}")
        lines.append(f"- 方向理由：{_text(item.get('impact_reason'), '未生成方向解释。')}")
        lines.append(f"- 量化证据：{_join(_list(item.get('quantitative_evidence')))}")
        lines.append(f"- 影响分计算：{_join(_list(item.get('score_breakdown')))}")
        lines.append(f"- 反方论点：{_text(item.get('counterpoint'), '需要结合后续数据复核。')}")
    lines.append("")


def _append_impact_score_meaning(lines: list[str], heading: str) -> None:
    lines.append(heading)
    lines.append("- `0.70 以上`：高影响事件，优先阅读和验证。")
    lines.append("- `0.50-0.70`：中高影响事件，可能影响某个画像或因子。")
    lines.append("- `0.30-0.50`：中等影响，更多是背景信息。")
    lines.append("- `0.30 以下`：低影响或噪音，通常不应单独决策。")
    lines.append("- 影响分表示事件重要程度，不等于上涨概率、下跌概率或预期涨跌幅；必须与方向、驱动因子和量化证据一起看。")
    lines.append("")


def _append_sec_summary(lines: list[str], filings: list[Any]) -> None:
    lines.append("### SEC 披露摘要")
    if not filings:
        lines.append("- 未采集到 SEC 披露。")
        lines.append("")
        return
    groups = {
        "重大披露": [],
        "财报披露": [],
        "持股/登记类披露": [],
        "其他披露": [],
    }
    for filing in filings:
        item = _dict(filing)
        metadata = _dict(item.get("raw_metadata"))
        group = str(metadata.get("display_group") or "其他披露")
        groups.setdefault(group, []).append(item)
    for group_name in ("重大披露", "财报披露", "持股/登记类披露", "其他披露"):
        items = groups.get(group_name, [])
        if not items:
            continue
        lines.append(f"#### {group_name}")
        lines.append("| 日期 | 中文标题 | 表单说明 | 英文原题 |")
        lines.append("|---|---|---|---|")
        for item in items[:5]:
            metadata = _dict(item.get("raw_metadata"))
            lines.append(
                f"| {_cell(item.get('filed_at'))} | {_cell(metadata.get('chinese_title') or item.get('title'))} | "
                f"{_cell(metadata.get('chinese_form_description'))} | {_cell(metadata.get('original_title'))} |"
            )
        lines.append("")


def _append_driver_scores(lines: list[str], scores: dict[str, Any]) -> None:
    lines.append("### 驱动因子评分")
    if not scores:
        lines.append("- 未生成驱动因子评分。")
        lines.append("")
        return
    lines.append("| 驱动因子 | 分数 |")
    lines.append("|---|---:|")
    for driver, score in scores.items():
        lines.append(f"| {_cell(driver)} | {_cell(_fmt_factor_score(score))} |")
    lines.append("")


def _append_scenarios(lines: list[str], scenarios: list[Any]) -> None:
    lines.append("### Bear/Base/Bull 情景预测")
    if not scenarios:
        lines.append("- 未生成情景预测。")
        lines.append("")
        return
    lines.append("| 情景 | 周期 | 区间低点 | 区间高点 | 触发条件 | 说明 |")
    lines.append("|---|---|---:|---:|---|---|")
    for scenario in scenarios:
        item = _dict(scenario)
        lines.append(
            f"| {_cell(item.get('name'))} | {_cell(item.get('horizon'))} | {_num(item.get('price_low'))} | "
            f"{_num(item.get('price_high'))} | {_cell(_join(item.get('trigger_conditions')))} | {_cell(item.get('rationale'))} |"
        )
    lines.append("")


def _append_validation(lines: list[str], layer1_checks: dict[str, bool], layer2_checks: dict[str, bool]) -> None:
    lines.append("## 一二层衔接验证")
    lines.append("| 检查项 | 结果 |")
    lines.append("|---|---|")
    for name, ok in layer1_checks.items():
        lines.append(f"| 第一层：{_cell(name)} | {_pass_text(ok)} |")
    for name, ok in layer2_checks.items():
        lines.append(f"| 第二层：{_cell(name)} | {_pass_text(ok)} |")
    lines.append("")


def _append_coverage_gaps(lines: list[str], gaps: list[Any]) -> None:
    lines.append("## 数据覆盖缺口")
    if not gaps:
        lines.append("- 当前数据覆盖未报告结构化缺口。")
        lines.append("")
        return
    lines.append("| 数据域 | 严重级别 | 置信度上限 | 缺口说明 | 建议来源 |")
    lines.append("|---|---|---|---|---|")
    for gap in gaps:
        item = _dict(gap)
        lines.append(
            f"| {_cell(item.get('label'))} | {_cell(item.get('severity'))} | {_cell(item.get('confidence_cap'))} | "
            f"{_cell(item.get('message'))} | {_cell(_join(_list(item.get('recommended_sources'))[:3]))} |"
        )
    lines.append("")


def _append_compliance(lines: list[str], checks: dict[str, bool]) -> None:
    lines.append("## 合规边界检查")
    lines.append("| 检查项 | 结果 |")
    lines.append("|---|---|")
    for name, ok in checks.items():
        lines.append(f"| {_cell(name)} | {_pass_text(ok)} |")
    lines.append("")


def _append_observations(lines: list[str], blocking_failures: list[str], warnings: list[Any], coverage: dict[str, Any], events: list[Any]) -> None:
    lines.append("## 异常观察与后续建议")
    if blocking_failures:
        lines.append("- 存在未通过检查项：" + _join(blocking_failures))
    else:
        lines.append("- 未发现阻断一二层测试的失败项。")
    if warnings:
        lines.append("- 第一层存在 warning，建议查看审计报告中的 Warning 明细并判断是否影响数据可信度。")
    if coverage.get("gaps"):
        lines.append("- 第二层数据覆盖仍有缺口，后续可补充结构化财务指标、行业数据、期权/资金流和回测结果，以提高分析置信度。")
    if _has_suspected_ai_misclassification(events):
        lines.append("- 仍观察到可能的 AI/FSD 分类噪音，建议继续扩充分类回归样本。")
    lines.append("- 本报告只提出系统测试与数据质量建议，不提供投资操作建议。")
    lines.append("")


def _has_suspected_ai_misclassification(events: list[Any]) -> bool:
    noisy_terms = ("financial", "capital", "billionaire")
    for event in events:
        item = _dict(event)
        title = str(item.get("title", "")).lower()
        if item.get("driver") == "FSD/Robotaxi/AI" and any(term in title for term in noisy_terms):
            return True
    return False


def _event_signal_fields_complete(events: list[Any]) -> bool:
    if not events:
        return False
    required = ("driver", "direction", "impact_score", "source_reliability")
    return all(all(_dict(event).get(field) not in (None, "") for field in required) for event in events)


def _event_display_time(event: dict[str, Any]) -> str:
    for key in ("published_at", "filed_at", "date", "date_time", "collected_at"):
        value = event.get(key)
        if value not in (None, ""):
            return _format_report_time(value)
    return ""


def _format_report_time(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return parsed.strftime("%Y-%m-%d %H:%M %Z").strip()


def _confidence_rank(value: Any) -> int:
    return CONFIDENCE_ORDER.get(str(value), 99)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _text(value: Any, default: str = "无") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _join(value: Any) -> str:
    return join_readable_items(value)


def _num(value: Any, digits: int = 2) -> str:
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


def _impact_level(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "无"
    if numeric >= 0.70:
        return "高影响事件"
    if numeric >= 0.50:
        return "中高影响事件"
    if numeric >= 0.30:
        return "中等影响事件"
    return "低影响或噪音"


def _cell(value: Any) -> str:
    text = _text(value).replace("\n", " ").replace("|", "\\|")
    return text[:220] + "..." if len(text) > 220 else text


def _pass_text(value: bool) -> str:
    return "通过" if value else "未通过"
