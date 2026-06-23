"""Chinese reporting for first-to-third-layer TSLA validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stock_agent.analysis.chinese_titles import event_title_with_translation
from stock_agent.analysis.report import FORBIDDEN_DECISION_FIELDS
from stock_agent.reporting.pdf import write_pdf_for_markdown
from stock_agent.reporting.text import join_readable_items

from . import (
    EVENT_DRIVEN,
    GROWTH_NARRATIVE,
    LONG_TERM_FUNDAMENTAL,
    RISK_CONTROL,
    SHORT_TERM_TRADER,
    SWING_TRADER,
    build_decision_plan,
)
from .cli import analysis_result_from_dict
from .report import build_decision_markdown


DEFAULT_PROFILES = (
    LONG_TERM_FUNDAMENTAL,
    GROWTH_NARRATIVE,
    EVENT_DRIVEN,
    SWING_TRADER,
    SHORT_TERM_TRADER,
    RISK_CONTROL,
)
REQUIRED_PLAN_FIELDS = (
    "profile",
    "current_bias",
    "confidence_level",
    "weighted_score",
    "supporting_factors",
    "risk_factors",
    "conditional_entry_plan",
    "exit_or_reduce_conditions",
    "stop_or_invalidation_conditions",
    "no_trade_conditions",
    "contrarian_view",
    "monitoring_checklist",
)
CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def write_layer123_test_outputs(
    *,
    collection_input: Path,
    analysis_input: Path,
    output_dir: Path,
    report_output: Path | None = None,
    validation_output: Path | None = None,
    profiles: tuple[str, ...] = DEFAULT_PROFILES,
) -> dict[str, Any]:
    """Write six-profile third-layer outputs and one Chinese validation report."""
    collection = json.loads(collection_input.read_text(encoding="utf-8"))
    analysis_payload = json.loads(analysis_input.read_text(encoding="utf-8"))
    analysis = analysis_result_from_dict(analysis_payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_output or output_dir / "layer123_test_report_tsla_zh.md"
    validation_path = validation_output or output_dir / "layer123_validation_tsla_live.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.parent.mkdir(parents=True, exist_ok=True)

    plan_payloads: dict[str, dict[str, Any]] = {}
    output_files: dict[str, str] = {
        "collection_json": str(collection_input),
        "analysis_json": str(analysis_input),
        "report_markdown": str(report_path),
        "validation_json": str(validation_path),
    }

    for profile in profiles:
        plan = build_decision_plan(analysis, profile)
        payload = plan.to_dict()
        plan_payloads[profile] = payload

        json_path = output_dir / f"decision_plan_{profile}_tsla_live.json"
        markdown_path = output_dir / f"decision_plan_{profile}_tsla_live.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(
            build_decision_markdown(
                plan,
                symbol=analysis.symbol,
                analysis_generated_at=analysis.generated_at,
                driver_scores=analysis.driver_scores,
            ),
            encoding="utf-8",
        )
        output_files[f"{profile}_json"] = str(json_path)
        output_files[f"{profile}_markdown"] = str(markdown_path)
        plan_pdf = write_pdf_for_markdown(markdown_path)
        if plan_pdf:
            output_files[f"{profile}_pdf"] = str(plan_pdf)

    report, validation = build_layer123_test_report(
        collection=collection,
        analysis=analysis_payload,
        plans=plan_payloads,
        output_files=output_files,
    )
    report_path.write_text(report, encoding="utf-8")
    report_pdf = write_pdf_for_markdown(report_path)
    if report_pdf:
        output_files["report_pdf"] = str(report_pdf)
        validation["output_files"] = dict(output_files)
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    return validation


def build_layer123_test_report(
    *,
    collection: dict[str, Any],
    analysis: dict[str, Any],
    plans: dict[str, dict[str, Any]],
    output_files: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    summary = _dict(collection.get("collection_summary"))
    quality = _dict(collection.get("data_quality_report"))
    source_inventory = _list(collection.get("source_inventory"))
    rss_sources = [source for source in source_inventory if _dict(source).get("name") == "rss"]
    rss_meta = _dict(_dict(rss_sources[-1]).get("raw_metadata")) if rss_sources else {}
    market = _dict(analysis.get("market_state"))
    coverage = _dict(analysis.get("data_coverage"))
    events = _list(analysis.get("event_signals"))
    scenarios = _list(analysis.get("scenario_forecasts"))

    layer1_checks = {
        "股票代码为 TSLA": summary.get("symbol") == "TSLA",
        "行情数据不少于 20 条": len(_list(collection.get("market_data"))) >= 20,
        "新闻事件大于 0 条": len(_list(collection.get("news_events"))) > 0,
        "SEC filings 大于 0 条": len(_list(collection.get("filings"))) > 0,
        "宏观数据大于 0 条": len(_list(collection.get("macro_data"))) > 0,
        "RSS 自动 feed 已生成": int(rss_meta.get("generated_feed_count") or 0) > 0,
    }
    layer2_checks = {
        "分析结果股票代码为 TSLA": analysis.get("symbol") == "TSLA",
        "最新收盘价存在": market.get("last_close") is not None,
        "最新交易日期存在": bool(market.get("last_date")),
        "事件信号大于 0 条": len(events) > 0,
        "前三情景包含 Bear/Base/Bull": {"Bear Case", "Base Case", "Bull Case"}.issubset(
            {str(item.get("name")) for item in scenarios if isinstance(item, dict)}
        ),
        "数据覆盖上限约束二层置信度": _confidence_rank(analysis.get("confidence_level")) <= _confidence_rank(coverage.get("confidence_cap")),
    }
    layer3_checks = {
        f"{profile} 字段完整": _plan_fields_complete(plan) for profile, plan in plans.items()
    }
    layer3_checks.update({
        "六类画像均已生成": set(DEFAULT_PROFILES).issubset(set(plans)),
        "第三层重要事件包含中文标题": _plans_include_chinese_event_titles(plans),
        "重要事件英文原题可追溯": _events_include_original_titles(events),
    })

    serialized = json.dumps({"collection": collection, "analysis": analysis, "plans": plans}, ensure_ascii=False)
    compliance_checks = {f"输出不含 {name}": name not in serialized for name in FORBIDDEN_DECISION_FIELDS}
    all_checks = {**layer1_checks, **layer2_checks, **layer3_checks, **compliance_checks}
    blocking_failures = [name for name, ok in all_checks.items() if not ok]
    warnings = _list(collection.get("warnings"))

    if blocking_failures:
        status = "未完全通过"
        conclusion = "三层测试已完成，但存在未通过检查项，需要复核后再作为稳定流程使用。"
    elif warnings or analysis.get("quality_downgrades") or coverage.get("gaps"):
        status = "通过，带降级观察"
        conclusion = "一二三层主流程跑通；第三层已生成六类条件化计划，但需要按数据覆盖缺口降级理解。"
    else:
        status = "通过"
        conclusion = "一二三层主流程跑通，六类画像、中文化展示和合规边界检查均通过。"

    validation = {
        "status": status,
        "blocking_failures": blocking_failures,
        "layer1_checks": layer1_checks,
        "layer2_checks": layer2_checks,
        "layer3_checks": layer3_checks,
        "compliance_checks": compliance_checks,
        "output_files": dict(output_files or {}),
    }

    lines: list[str] = []
    lines.append("# TSLA 一二三层测试中文报告")
    lines.append("")
    lines.append("## 测试结论")
    lines.append(f"- 结论：{conclusion}")
    lines.append(f"- 测试状态：{status}")
    lines.append(f"- 生成时间：{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")
    lines.append("- 合规声明：本报告仅用于系统测试和研究辅助，不构成投资建议；第三层内容为条件化计划，不是无条件买卖指令。")
    lines.append("")

    _append_inputs(lines, collection, analysis, rss_meta)
    _append_layer2_summary(lines, analysis)
    _append_profile_comparison(lines, plans)
    _append_score_meaning(lines)
    _append_important_events(lines, events)
    _append_plan_summary(lines, plans, _dict(analysis.get("driver_scores")))
    _append_coverage_gaps(lines, _list(coverage.get("gaps")))
    _append_compliance(lines, compliance_checks)
    _append_observations(lines, blocking_failures, warnings, analysis, plans)
    _append_outputs(lines, validation["output_files"])
    return "\n".join(lines).rstrip() + "\n", validation


def _append_inputs(lines: list[str], collection: dict[str, Any], analysis: dict[str, Any], rss_meta: dict[str, Any]) -> None:
    summary = _dict(collection.get("collection_summary"))
    lines.append("## 输入数据")
    lines.append(f"- 第一层股票代码：{_text(summary.get('symbol'))}")
    lines.append(f"- 公司名称：{_text(summary.get('company_name'))}")
    lines.append(f"- 第一层采集时间：{_text(summary.get('collection_time'))}")
    lines.append(f"- 第二层分析时间：{_text(analysis.get('generated_at'))}")
    lines.append(f"- 行情/新闻/SEC/宏观数量：{len(_list(collection.get('market_data')))} / {len(_list(collection.get('news_events')))} / {len(_list(collection.get('filings')))} / {len(_list(collection.get('macro_data')))}")
    lines.append(f"- RSS 自动 feed：生成 {rss_meta.get('generated_feed_count', 0)} 个，symbols={_join(rss_meta.get('symbols'))}")
    lines.append("")


def _append_layer2_summary(lines: list[str], analysis: dict[str, Any]) -> None:
    market = _dict(analysis.get("market_state"))
    coverage = _dict(analysis.get("data_coverage"))
    lines.append("## 二层摘要")
    lines.append(f"- 分析股票代码：{_text(analysis.get('symbol'))}")
    lines.append(f"- 二层置信度：{_text(analysis.get('confidence_level'))}")
    lines.append(f"- 数据覆盖等级/上限：{_text(coverage.get('coverage_level'))} / {_text(coverage.get('confidence_cap'))}")
    lines.append(f"- 最新收盘价/日期：{_num(market.get('last_close'))} / {_text(market.get('last_date'))}")
    lines.append(f"- 5 日/20 日涨跌幅：{_num(market.get('change_5d_pct'))}% / {_num(market.get('change_20d_pct'))}%")
    lines.append(f"- 支撑/压力/ATR：{_num(market.get('support_level'))} / {_num(market.get('resistance_level'))} / {_num(market.get('atr_14'))}")
    lines.append(f"- 趋势标签：{_text(market.get('trend_label'))}")
    lines.append("")


def _append_profile_comparison(lines: list[str], plans: dict[str, dict[str, Any]]) -> None:
    lines.append("## 六类画像结果对比")
    lines.append("| 画像 | 当前倾向 | 第三层置信度 | 总得分 | 数据覆盖等级 | 置信度上限 |")
    lines.append("|---|---|---|---:|---|---|")
    for profile in DEFAULT_PROFILES:
        plan = _dict(plans.get(profile))
        profile_payload = _dict(plan.get("profile"))
        coverage = _dict(plan.get("profile_coverage"))
        lines.append(
            f"| {_cell(profile_payload.get('label') or profile)} | {_cell(plan.get('current_bias'))} | "
            f"{_cell(plan.get('confidence_level'))} | {_num(plan.get('weighted_score'), 3)} | "
            f"{_cell(coverage.get('coverage_level'))} | {_cell(coverage.get('confidence_cap'))} |"
        )
    lines.append("")


def _append_score_meaning(lines: list[str]) -> None:
    lines.append("## 得分含义说明")
    lines.append("- 总得分 = Σ(因子权重 x 当前因子得分)，因子得分范围约为 -1 到 1，权重合计约为 100%。")
    lines.append("- `> 0.18`：条件偏多，说明当前证据整体偏正，但仍需满足触发条件。")
    lines.append("- `-0.18 到 0.18`：区间观察，说明多空证据不够悬殊，优先等待确认。")
    lines.append("- `< -0.18`：条件偏谨慎，说明风险或负面证据占优。")
    lines.append("- `LOW 置信度`：低置信度观察，数据质量或覆盖不足时不应把分数当作强信号。")
    lines.append("")


def _append_important_events(lines: list[str], events: list[Any]) -> None:
    lines.append("## 重要资讯中文摘要")
    if not events:
        lines.append("- 未生成重要事件信号。")
        lines.append("")
        return
    _append_impact_score_meaning(lines)
    lines.append("| 排名 | 事件层级 | 解释框架 | 发布时间 | 驱动因子 | 方向 | 影响等级 | 来源 | 中文标题 / 原题译文 |")
    lines.append("|---:|---|---|---|---|---|---|---|---|")
    for index, event in enumerate(events[:10], 1):
        item = _dict(event)
        title = _text(item.get("title"))
        lines.append(
            f"| {index} | {_cell(item.get('event_scope'))} | {_cell(_framework_display(item))} | {_cell(_event_display_time(item))} | "
            f"{_cell(item.get('driver'))} | {_cell(item.get('direction'))} | "
            f"{_cell(_impact_level(item.get('impact_score')))} | {_cell(item.get('source'))} | "
            f"{_cell(event_title_with_translation(title, item.get('driver')))} |"
        )
    lines.append("")
    lines.append("### 事件影响分解释")
    for index, event in enumerate(events[:10], 1):
        item = _dict(event)
        title = _text(item.get("title"))
        lines.append(f"**{index}. {event_title_with_translation(title, item.get('driver'))}**")
        lines.append(f"- 事件层级：{_text(item.get('event_scope'), '公司级事件')}")
        lines.append(f"- 解读框架：{_framework_display(item)}")
        lines.append(f"- 发布时间：{_text(_event_display_time(item), '未提供')}")
        lines.append(f"- 英文原题：{_text(title)}")
        lines.append(f"- 影响等级：{_impact_level(item.get('impact_score'))}；具体影响分：{_num(item.get('impact_score'), 3)}")
        lines.append(f"- 方向理由：{_text(item.get('impact_reason'), '未生成方向解释。')}")
        lines.append(f"- 量化证据：{_join(_list(item.get('quantitative_evidence')))}")
        lines.append(f"- 影响分计算：{_join(_list(item.get('score_breakdown')))}")
        lines.append(f"- 反方论点：{_text(item.get('counterpoint'), '需要结合后续数据复核。')}")
    lines.append("")


def _append_impact_score_meaning(lines: list[str]) -> None:
    lines.append("### 影响分含义说明")
    lines.append("- `0.70 以上`：高影响事件，优先阅读和验证。")
    lines.append("- `0.50-0.70`：中高影响事件，可能影响某个画像或因子。")
    lines.append("- `0.30-0.50`：中等影响，更多是背景信息。")
    lines.append("- `0.30 以下`：低影响或噪音，通常不应单独决策。")
    lines.append("- 影响分表示事件重要程度，不等于上涨概率、下跌概率或预期涨跌幅；必须与方向、驱动因子和量化证据一起看。")
    lines.append("")


def _append_plan_summary(lines: list[str], plans: dict[str, dict[str, Any]], driver_scores: dict[str, Any]) -> None:
    lines.append("## 条件化计划摘要")
    for profile in DEFAULT_PROFILES:
        plan = _dict(plans.get(profile))
        label = _dict(plan.get("profile")).get("label") or profile
        current_bias = _text(plan.get("current_bias"))
        total_score = _num(plan.get("weighted_score"), 3)
        lines.append(f"### {_text(label)}")
        lines.append(f"- 当前倾向：{current_bias}；置信度：{_text(plan.get('confidence_level'))}；总得分：{total_score}")
        lines.append("- 计算方式：各因子加权贡献相加，因子得分范围约为 -1 到 1，权重合计约为 100%。")
        lines.append(f"- 当前解读：{_score_interpretation(current_bias)}")
        _append_factor_contribution_table(lines, plan, driver_scores)
        lines.append("- 支持因素：" + _join(_list(plan.get("supporting_factors"))[:2]))
        lines.append("- 风险因素：" + _join(_list(plan.get("risk_factors"))[:2]))
        lines.append("- 条件化参与：" + _join(_list(plan.get("conditional_entry_plan"))[:2]))
        lines.append("- 不交易条件：" + _join(_list(plan.get("no_trade_conditions"))[:2]))
    lines.append("")


def _append_factor_contribution_table(lines: list[str], plan: dict[str, Any], driver_scores: dict[str, Any]) -> None:
    profile = _dict(plan.get("profile"))
    weights = _dict(profile.get("weights"))
    lines.append("| 因子 | 画像权重 | 当前得分 | 加权贡献 |")
    lines.append("|---|---:|---:|---:|")
    for driver, weight in sorted(weights.items(), key=lambda item: _float(item[1]), reverse=True):
        numeric_weight = _float(weight)
        if numeric_weight <= 0:
            continue
        score = driver_scores.get(driver)
        numeric_score = _float(score)
        contribution = numeric_weight * numeric_score
        lines.append(f"| {_cell(driver)} | {numeric_weight:.0%} | {_cell(_fmt_factor_score(score))} | {_num(contribution, 3)} |")
    lines.append(f"- 贡献合计：{_num(plan.get('weighted_score'), 3)}")
    lines.append("")


def _append_coverage_gaps(lines: list[str], gaps: list[Any]) -> None:
    lines.append("## 数据缺口")
    if not gaps:
        lines.append("- 当前二层未报告结构化数据缺口。")
        lines.append("")
        return
    lines.append("| 数据域 | 严重级别 | 置信度上限 | 缺口说明 |")
    lines.append("|---|---|---|---|")
    for gap in gaps:
        item = _dict(gap)
        lines.append(f"| {_cell(item.get('label'))} | {_cell(item.get('severity'))} | {_cell(item.get('confidence_cap'))} | {_cell(item.get('message'))} |")
    lines.append("")


def _append_compliance(lines: list[str], checks: dict[str, bool]) -> None:
    lines.append("## 合规边界检查")
    lines.append("| 检查项 | 结果 |")
    lines.append("|---|---|")
    for name, ok in checks.items():
        lines.append(f"| {_cell(name)} | {_pass_text(ok)} |")
    lines.append("- 第三层输出为条件化计划、失效条件、不交易条件和反方观点；未连接券商下单能力。")
    lines.append("")


def _append_observations(
    lines: list[str],
    blocking_failures: list[str],
    warnings: list[Any],
    analysis: dict[str, Any],
    plans: dict[str, dict[str, Any]],
) -> None:
    lines.append("## 异常观察")
    if blocking_failures:
        lines.append("- 未通过检查项：" + _join(blocking_failures))
    else:
        lines.append("- 未发现阻断一二三层测试的失败项。")
    if warnings:
        lines.append(f"- 第一层存在 {len(warnings)} 条 warning，第三层应按降级后的置信度理解。")
    if analysis.get("quality_downgrades"):
        lines.append("- 二层存在质量降级原因：" + _join(_list(analysis.get("quality_downgrades"))[:3]))
    low_conf_profiles = [
        _dict(plan.get("profile")).get("label") or profile
        for profile, plan in plans.items()
        if _dict(plan).get("confidence_level") == "LOW"
    ]
    if low_conf_profiles:
        lines.append("- LOW 置信度画像：" + _join(low_conf_profiles))
    lines.append("- 后续建议只针对系统测试：继续补结构化财务指标、期权/资金流、行业数据和回测覆盖。")
    lines.append("")


def _append_outputs(lines: list[str], output_files: dict[str, str]) -> None:
    lines.append("## 输出文件")
    labels = {
        "collection_json": "第一层采集 JSON",
        "analysis_json": "第二层分析 JSON",
        "report_markdown": "一二三层中文综合报告",
        "validation_json": "校验结果 JSON",
    }
    for key, label in labels.items():
        if output_files.get(key):
            lines.append(f"- {label}：`{output_files[key]}`")
    for profile in DEFAULT_PROFILES:
        if output_files.get(f"{profile}_json"):
            lines.append(f"- {profile} JSON：`{output_files[f'{profile}_json']}`")
        if output_files.get(f"{profile}_markdown"):
            lines.append(f"- {profile} Markdown：`{output_files[f'{profile}_markdown']}`")
    lines.append("")


def _plan_fields_complete(plan: dict[str, Any]) -> bool:
    if not plan:
        return False
    return all(plan.get(field) not in (None, "", []) for field in REQUIRED_PLAN_FIELDS)


def _plans_include_chinese_event_titles(plans: dict[str, dict[str, Any]]) -> bool:
    text = json.dumps(plans, ensure_ascii=False)
    return any(term in text for term in ("自动驾驶", "监管", "交付", "评级", "资金", "财经新闻", "披露"))


def _plans_include_original_titles(plans: dict[str, dict[str, Any]]) -> bool:
    text = json.dumps(plans, ensure_ascii=False)
    return "英文原题：" in text


def _events_include_original_titles(events: list[Any]) -> bool:
    return any(bool(_dict(event).get("title")) for event in events)


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


def _event_display_time(event: dict[str, Any]) -> str:
    for key in ("published_at", "filed_at", "date", "date_time", "collected_at"):
        value = event.get(key)
        if value not in (None, ""):
            return _format_report_time(value)
    return ""


def _framework_display(event: dict[str, Any]) -> str:
    return _text(event.get("interpretation_framework"), "无")


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


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score_interpretation(current_bias: str) -> str:
    if current_bias == "低置信度观察":
        return "低置信度观察，数据质量或覆盖不足时不应把分数当作强信号。"
    if current_bias == "条件偏多":
        return "条件偏多，当前证据整体偏正，但仍需满足触发条件。"
    if current_bias == "条件偏谨慎":
        return "条件偏谨慎，风险或负面证据占优。"
    return "区间观察，多空证据不够悬殊，优先等待确认。"


def _cell(value: Any) -> str:
    text = _text(value).replace("\n", " ").replace("|", "\\|")
    return text[:220] + "..." if len(text) > 220 else text


def _pass_text(value: bool) -> str:
    return "通过" if value else "未通过"
