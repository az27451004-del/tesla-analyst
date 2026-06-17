"""Quality gates for analysis results."""

from __future__ import annotations

from typing import Any, Iterable

from stock_agent.data_coverage import DataCoverageReport, evaluate_data_coverage

from .models import EventSignal, MarketState
from .utils import dedupe


def build_quality_downgrades(
    prices: list[dict[str, Any]],
    events: tuple[EventSignal, ...],
    warnings: Iterable[str],
    missing_requirements: Iterable[str],
    macro_count: int,
    financial_metric_count: int,
    options_count: int,
) -> list[str]:
    downgrades = [str(warning) for warning in warnings if warning]
    missing = {str(item) for item in missing_requirements if item}
    if not prices:
        downgrades.append("缺少价格数据，无法形成高置信度市场状态。")
    elif not any(item.get("volume") is not None for item in prices):
        downgrades.append("缺少成交量数据，技术面判断降级。")
    if len(events) < 3:
        downgrades.append("事件数量较少，事件驱动结论置信度较低。")
    if macro_count == 0 and "macro_data" in missing:
        downgrades.append("缺少宏观数据，利率/美元/纳指因子降级。")
    if financial_metric_count == 0 and ("financial_metrics" in missing or "filings" in missing):
        downgrades.append("缺少财务指标或披露数据，基本面判断降级。")
    if options_count == 0 and "options_data" in missing:
        downgrades.append("缺少期权数据，资金流和波动率判断降级。")
    if looks_like_sample(prices, events, warnings):
        downgrades.append("检测到样例或 fictional 数据，不能作为真实投资判断。")
    return dedupe(downgrades)


def build_data_coverage_report(
    *,
    prices: list[dict[str, Any]],
    event_signals: tuple[EventSignal, ...],
    warnings: Iterable[str],
    macro_count: int,
    financial_metric_count: int,
    options_count: int,
    filings_count: int,
    official_events_count: int,
    industry_count: int,
    broker_account_count: int,
    research_report_count: int,
    has_backtest: bool,
) -> DataCoverageReport:
    return evaluate_data_coverage(
        has_market_data=bool(prices),
        has_volume=any(item.get("volume") is not None for item in prices),
        has_filings=filings_count > 0,
        has_financial_metrics=financial_metric_count > 0,
        has_research_reports=research_report_count > 0,
        has_macro_data=macro_count > 0,
        has_industry_data=industry_count > 0,
        has_official_events=official_events_count > 0,
        has_options_data=options_count > 0,
        has_broker_account_data=broker_account_count > 0,
        has_backtest=has_backtest,
        sample_data_detected=looks_like_sample(prices, event_signals, warnings),
        stale_market_data=False,
    )


def confidence_level(market: MarketState, downgrades: list[str]) -> str:
    if market.last_close is None or len(downgrades) >= 4:
        return "LOW"
    if downgrades:
        return "MEDIUM"
    return "HIGH"


def looks_like_sample(prices: list[dict[str, Any]], events: tuple[EventSignal, ...], warnings: Iterable[str]) -> bool:
    blob = " ".join(
        [str(item.get("source", "")) + str(item.get("raw_metadata", "")) for item in prices]
        + [event.title + event.source + event.evidence for event in events]
        + [str(warning) for warning in warnings]
    ).lower()
    return any(term in blob for term in ("sample", "fictional", "example.com"))
