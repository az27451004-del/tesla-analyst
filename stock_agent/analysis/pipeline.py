"""Public orchestration functions for the second analysis layer."""

from __future__ import annotations

from typing import Any, Iterable

from stock_agent.data_coverage import confidence_min

from .events import build_driver_scores, build_event_signals
from .market import build_market_state, build_scenario_forecasts, clean_prices
from .models import AnalysisResult
from .quality import build_data_coverage_report, build_quality_downgrades, confidence_level
from .utils import field_value, now_iso


def analyze_collection(result: Any) -> AnalysisResult:
    """Analyze a stock_agent.collection.CollectionResult without adding advice."""
    summary = field_value(result, "collection_summary")
    symbol = field_value(summary, "symbol", default="") or "UNKNOWN"
    prices = list(field_value(result, "market_data", default=[]) or [])
    macro_data = list(field_value(result, "macro_data", default=[]) or [])
    industry_data = list(field_value(result, "industry_data", default=[]) or [])
    events: list[Any] = []
    events.extend(field_value(result, "news_events", default=[]) or [])
    events.extend(field_value(result, "official_events", default=[]) or [])
    events.extend(field_value(result, "filings", default=[]) or [])
    warnings = [str(field_value(item, "message", default=item)) for item in field_value(result, "warnings", default=[]) or []]
    quality = field_value(result, "data_quality_report")
    missing = list(field_value(quality, "missing_requirements", default=[]) or [])
    return analyze_market_events(
        symbol=symbol,
        prices=prices,
        events=events,
        warnings=warnings,
        missing_requirements=missing,
        macro_data=macro_data,
        industry_data=industry_data,
        macro_count=len(macro_data),
        financial_metric_count=len(field_value(result, "financial_metrics", default=[]) or []),
        options_count=len(field_value(result, "options_data", default=[]) or []),
        filings_count=len(field_value(result, "filings", default=[]) or []),
        official_events_count=len(field_value(result, "official_events", default=[]) or []),
        industry_count=len(industry_data),
        broker_account_count=len(field_value(result, "broker_account_data", default=[]) or []),
        research_report_count=len(field_value(result, "research_reports", default=[]) or []),
    )


def analyze_market_events(
    *,
    symbol: str,
    prices: Iterable[Any],
    events: Iterable[Any],
    warnings: Iterable[str] = (),
    missing_requirements: Iterable[str] = (),
    macro_data: Iterable[Any] = (),
    industry_data: Iterable[Any] = (),
    macro_count: int = 0,
    financial_metric_count: int = 0,
    options_count: int = 0,
    filings_count: int = 0,
    official_events_count: int = 0,
    industry_count: int = 0,
    broker_account_count: int = 0,
    research_report_count: int = 0,
    has_backtest: bool = False,
) -> AnalysisResult:
    """Build the second-layer analysis signal model from market data and events."""
    normalized_prices = clean_prices(prices)
    market_state = build_market_state(symbol, normalized_prices)
    event_signals = build_event_signals(events)
    macro_points = tuple(macro_data)
    industry_points = tuple(industry_data)
    driver_scores = build_driver_scores(event_signals, market_state, macro_data=macro_points, industry_data=industry_points)
    scenarios = build_scenario_forecasts(market_state)
    warning_messages = tuple(str(item) for item in warnings if item)
    missing = tuple(str(item) for item in missing_requirements if item)
    downgrades = build_quality_downgrades(
        normalized_prices,
        event_signals,
        warning_messages,
        missing,
        macro_count or len(macro_points),
        financial_metric_count,
        options_count,
    )
    coverage = build_data_coverage_report(
        prices=normalized_prices,
        event_signals=event_signals,
        warnings=warning_messages,
        macro_count=macro_count or len(macro_points),
        financial_metric_count=financial_metric_count,
        options_count=options_count,
        filings_count=filings_count,
        official_events_count=official_events_count,
        industry_count=industry_count or len(industry_points),
        broker_account_count=broker_account_count,
        research_report_count=research_report_count,
        has_backtest=has_backtest,
    )
    confidence = confidence_min(confidence_level(market_state, downgrades), coverage.confidence_cap)
    return AnalysisResult(
        symbol=symbol.upper().strip(),
        generated_at=now_iso(),
        market_state=market_state,
        event_signals=event_signals,
        driver_scores=driver_scores,
        scenario_forecasts=scenarios,
        quality_downgrades=tuple(downgrades),
        confidence_level=confidence,
        data_coverage=coverage,
    )
