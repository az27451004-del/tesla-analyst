from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_collection_audit_markdown(payload: dict[str, Any]) -> str:
    summary = _dict(payload.get("collection_summary"))
    quality = _dict(payload.get("data_quality_report"))
    checks = _dict(quality.get("checks"))

    lines: list[str] = []
    lines.append(f"# 采集结果审计报告：{_text(summary.get('symbol'), 'UNKNOWN')}")
    lines.append("")
    lines.append(f"- 生成时间：{_now_iso()}")
    lines.append("- 用途：仅用于第一层信息收集结果审计。")
    lines.append("- 声明：本报告不构成投资建议，不提供买卖判断、目标价、价格预测或交易计划。")
    lines.append("")

    lines.append("## 采集摘要")
    lines.append(f"- 股票代码：{_text(summary.get('symbol'))}")
    lines.append(f"- 公司名称：{_text(summary.get('company_name'))}")
    lines.append(f"- 采集时间：{_text(summary.get('collection_time'))}")
    lines.append(f"- 总体质量：{_quality_text(summary.get('overall_quality'))}")
    lines.append(f"- 是否可进入后续分析：{_bool_text(summary.get('can_generate_analysis'))}")
    lines.append(f"- 置信度上限：{_quality_text(summary.get('confidence_cap'))}")
    lines.append(f"- 新鲜度状态：{_freshness_text(summary.get('freshness_status'))}")
    lines.append(f"- 已使用数据源：{_join_or_none(summary.get('data_sources_used'))}")
    lines.append(f"- 失败数据源：{_join_or_none(summary.get('data_sources_failed'))}")
    lines.append("")

    lines.append("## 数据覆盖")
    lines.append("| 数据集 | 记录数 |")
    lines.append("|---|---:|")
    coverage_fields = [
        ("行情数据", "market_data"),
        ("SEC 披露", "filings"),
        ("官方事件", "official_events"),
        ("财务指标", "financial_metrics"),
        ("新闻事件", "news_events"),
        ("宏观数据", "macro_data"),
        ("行业数据", "industry_data"),
        ("期权数据", "options_data"),
        ("券商账户数据", "broker_account_data"),
        ("研究报告", "research_reports"),
    ]
    for label, key in coverage_fields:
        lines.append(f"| {label} | {len(_list(payload.get(key)))} |")
    lines.append("")

    lines.append("## 数据来源清单")
    sources = _list(payload.get("source_inventory"))
    if sources:
        lines.append("| 来源 | 是否启用 | 是否使用 | 是否失败 | 可信度 | 记录数 | 失败原因 |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for source in sources:
            item = _dict(source)
            lines.append(
                "| "
                f"{_cell(item.get('name'))} | "
                f"{_bool_text(item.get('enabled'))} | "
                f"{_bool_text(item.get('used'))} | "
                f"{_bool_text(item.get('failed'))} | "
                f"{_num(item.get('reliability'))} | "
                f"{_text(item.get('records_collected'), '0')} | "
                f"{_cell(item.get('failure_reason') or '无')} |"
            )
    else:
        lines.append("未采集到数据")
    lines.append("")

    lines.append("## 数据质量")
    lines.append(f"- 总体质量：{_quality_text(quality.get('overall_quality'))}")
    lines.append(f"- 是否可进入后续分析：{_bool_text(quality.get('can_generate_analysis'))}")
    lines.append(f"- 置信度上限：{_quality_text(quality.get('confidence_cap'))}")
    lines.append(f"- 缺失需求：{_join_or_none(quality.get('missing_requirements'))}")
    lines.append(f"- 警告摘要：{_join_or_none(quality.get('warnings'))}")
    lines.append(f"- 冲突数量：{_text(checks.get('conflict_count'), str(len(_list(payload.get('conflicts')))))}")
    lines.append(f"- 合并重复事件数：{_text(checks.get('duplicate_event_count'), '0')}")
    lines.append(f"- 未知来源数量：{_text(checks.get('unknown_source_count'), '0')}")
    lines.append(f"- 低可信度记录数：{_text(checks.get('low_reliability_record_count'), '0')}")
    lines.append("")

    _append_warning_records(lines, payload)
    _append_conflict_records(lines, payload)
    _append_market_snapshot(lines, payload)
    _append_macro_snapshot(lines, payload)
    _append_recent_filings(lines, payload)
    _append_recent_news(lines, payload)
    _append_broker_status(lines, payload)

    return "\n".join(lines).rstrip() + "\n"


def _append_warning_records(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 警告记录")
    warnings = _list(payload.get("warnings"))
    if not warnings:
        lines.append("未采集到数据")
        lines.append("")
        return
    lines.append("| 严重级别 | 来源 | 代码 | 信息 |")
    lines.append("|---|---|---|---|")
    for warning in warnings:
        item = _dict(warning)
        lines.append(
            f"| {_cell(item.get('severity'))} | {_cell(item.get('source'))} | "
            f"{_cell(item.get('code'))} | {_cell(item.get('message'))} |"
        )
    lines.append("")


def _append_conflict_records(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 冲突记录")
    conflicts = _list(payload.get("conflicts"))
    if not conflicts:
        lines.append("未采集到数据")
        lines.append("")
        return
    lines.append("| 类型 | 冲突来源 | 优先值 | 是否需要复核 | 原因 |")
    lines.append("|---|---|---|---:|---|")
    for conflict in conflicts:
        item = _dict(conflict)
        lines.append(
            f"| {_cell(item.get('conflict_type'))} | {_cell(_join_or_none(item.get('conflicting_sources')))} | "
            f"{_cell(item.get('preferred_value'))} | {_bool_text(item.get('requires_review'))} | {_cell(item.get('reason'))} |"
        )
    lines.append("")


def _append_market_snapshot(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 行情快照")
    points = sorted(_list(payload.get("market_data")), key=lambda item: str(_dict(item).get("date_time", "")))
    if not points:
        lines.append("未采集到数据")
        lines.append("")
        return
    lines.append("| 日期 | 开盘 | 最高 | 最低 | 收盘 | 成交量 | 来源 | 可信度 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|---:|")
    for point in points[-5:]:
        item = _dict(point)
        lines.append(
            f"| {_cell(item.get('date_time'))} | {_num(item.get('open'))} | {_num(item.get('high'))} | "
            f"{_num(item.get('low'))} | {_num(item.get('close'))} | {_num(item.get('volume'))} | "
            f"{_cell(item.get('source'))} | {_num(item.get('source_reliability'))} |"
        )
    lines.append("")


def _append_macro_snapshot(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 宏观数据快照")
    points = _list(payload.get("macro_data"))
    if not points:
        lines.append("未采集到数据")
        lines.append("")
        return
    lines.append("| 指标 | 数值 | 日期 | 单位 | 来源 | 可信度 |")
    lines.append("|---|---:|---|---|---|---:|")
    for point in points:
        item = _dict(point)
        lines.append(
            f"| {_cell(item.get('indicator_name'))} | {_num(item.get('value'))} | {_cell(item.get('date'))} | "
            f"{_cell(item.get('unit'))} | {_cell(item.get('source'))} | {_num(item.get('source_reliability'))} |"
        )
    lines.append("")


def _append_recent_filings(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 最近 SEC 披露")
    filings = sorted(_list(payload.get("filings")), key=lambda item: str(_dict(item).get("filed_at", "")), reverse=True)
    if not filings:
        lines.append("未采集到数据")
        lines.append("")
        return
    lines.append("| 表单 | 披露时间 | 报告期结束 | Accession | 来源 | 可信度 | URL |")
    lines.append("|---|---|---|---|---|---:|---|")
    for filing in filings[:10]:
        item = _dict(filing)
        lines.append(
            f"| {_cell(item.get('filing_type'))} | {_cell(item.get('filed_at'))} | {_cell(item.get('period_end'))} | "
            f"{_cell(item.get('accession_number'))} | {_cell(item.get('source'))} | "
            f"{_num(item.get('source_reliability'))} | {_link(item.get('url'))} |"
        )
    lines.append("")


def _append_recent_news(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 最近新闻")
    events = sorted(_list(payload.get("news_events")), key=lambda item: str(_dict(item).get("published_at", "")), reverse=True)
    if not events:
        lines.append("未采集到数据")
        lines.append("")
        return
    lines.append("| 发布时间 | 标题 | 发布方 | 来源 | 可信度 | URL |")
    lines.append("|---|---|---|---|---:|---|")
    for event in events[:10]:
        item = _dict(event)
        lines.append(
            f"| {_cell(item.get('published_at'))} | {_cell(item.get('title'))} | {_cell(item.get('publisher'))} | "
            f"{_cell(item.get('source'))} | {_num(item.get('source_reliability'))} | {_link(item.get('url'))} |"
        )
    lines.append("")


def _append_broker_status(lines: list[str], payload: dict[str, Any]) -> None:
    lines.append("## 券商状态")
    summary = _dict(payload.get("collection_summary"))
    status = _dict(summary.get("ibkr_status"))
    broker_records = _list(payload.get("broker_account_data"))
    lines.append(f"- IBKR 是否启用：{_bool_text(status.get('enabled'))}")
    lines.append(f"- IBKR 是否连接：{_bool_text(status.get('connected'))}")
    lines.append(f"- 是否允许账户数据：{_bool_text(status.get('account_data_allowed'))}")
    lines.append(f"- 券商账户记录数：{len(broker_records)}")
    if not broker_records:
        lines.append("- 券商账户数据：未采集到数据")
    lines.append("")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, default: str = "无") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _bool_text(value: Any) -> str:
    return "是" if bool(value) else "否"


def _join_or_none(value: Any) -> str:
    items = _list(value)
    if not items:
        return "无"
    return ", ".join(str(item) for item in items)


def _num(value: Any) -> str:
    if value is None or value == "":
        return "无"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _cell(value: Any) -> str:
    text = _text(value).replace("\n", " ").replace("|", "\\|")
    return text[:240] + "..." if len(text) > 240 else text


def _link(url: Any) -> str:
    text = _text(url)
    if text == "无":
        return "无"
    return f"[链接]({text})"


def _quality_text(value: Any) -> str:
    text = _text(value)
    mapping = {
        "HIGH": "高",
        "MEDIUM": "中",
        "LOW": "低",
        "INSUFFICIENT": "不足",
    }
    return f"{mapping[text]} ({text})" if text in mapping else text


def _freshness_text(value: Any) -> str:
    text = _text(value)
    mapping = {
        "FRESH": "新鲜",
        "RECENT": "较新",
        "STALE": "过期",
        "NO_MARKET_DATA": "无行情数据",
        "UNKNOWN": "未知",
    }
    return f"{mapping[text]} ({text})" if text in mapping else text


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
