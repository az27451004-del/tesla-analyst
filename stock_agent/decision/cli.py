"""Standalone CLI for the third decision expression layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stock_agent.analysis.models import AnalysisResult, EventSignal, MarketState, ScenarioForecast
from stock_agent.data_coverage import DataCoverageReport, DataGap, DataSourceRoadmapItem
from stock_agent.reporting import write_pdf_for_markdown

from . import LONG_TERM_FUNDAMENTAL, build_decision_plan
from .report import build_decision_markdown


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        content, _, _ = build_decision_output(
            input_path=Path(args.input),
            investor_type=args.investor_type,
            horizon=args.horizon,
            output_format=args.format,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"Decision plan written to {output}")
        if args.format == "markdown":
            pdf_path = write_pdf_for_markdown(output)
            if pdf_path:
                print(f"PDF report written to {pdf_path}")
            else:
                print("PDF report was not generated because ReportLab is unavailable.")
    else:
        print(content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the independent third-layer decision plan generator")
    parser.add_argument("--input", required=True, help="AnalysisResult JSON input path")
    parser.add_argument("--output", help="Output path. If omitted, content is printed to stdout")
    parser.add_argument("--format", choices=("json", "markdown"), default="json", help="Output format")
    parser.add_argument("--investor-type", default=LONG_TERM_FUNDAMENTAL, help="Investor profile for the plan")
    parser.add_argument("--horizon", default="", help="Optional investment or trading horizon override")
    return parser


def build_decision_output(
    *,
    input_path: Path,
    investor_type: str,
    horizon: str,
    output_format: str,
) -> tuple[str, AnalysisResult, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    analysis = analysis_result_from_dict(payload)
    plan = build_decision_plan(analysis, investor_type, horizon)
    if output_format == "markdown":
        content = build_decision_markdown(
            plan,
            symbol=analysis.symbol,
            analysis_generated_at=analysis.generated_at,
            driver_scores=analysis.driver_scores,
        )
    else:
        content = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
    return content, analysis, plan


def analysis_result_from_dict(payload: dict[str, Any]) -> AnalysisResult:
    """Rebuild the second-layer result model from AnalysisResult.to_dict() output."""
    if not isinstance(payload, dict):
        raise ValueError("input must be an AnalysisResult JSON object")
    if "data_coverage" not in payload:
        raise ValueError("input JSON must include data_coverage from AnalysisResult.to_dict()")

    symbol = str(payload.get("symbol") or "UNKNOWN").upper().strip()
    market_payload = dict(_mapping(payload.get("market_state")))
    market_payload.setdefault("symbol", symbol)

    return AnalysisResult(
        symbol=symbol,
        generated_at=str(payload.get("generated_at") or ""),
        market_state=_market_state_from_dict(market_payload),
        event_signals=tuple(_event_signal_from_dict(item) for item in _sequence(payload.get("event_signals"))),
        driver_scores={str(key): float(value) for key, value in _mapping(payload.get("driver_scores")).items()},
        scenario_forecasts=tuple(
            _scenario_forecast_from_dict(item) for item in _sequence(payload.get("scenario_forecasts"))
        ),
        quality_downgrades=tuple(str(item) for item in _sequence(payload.get("quality_downgrades"))),
        confidence_level=str(payload.get("confidence_level") or "LOW"),
        data_coverage=_data_coverage_from_dict(_mapping(payload.get("data_coverage"))),
    )


def _market_state_from_dict(payload: dict[str, Any]) -> MarketState:
    return MarketState(
        symbol=str(payload.get("symbol") or "UNKNOWN"),
        last_close=_float_or_none(payload.get("last_close")),
        last_date=str(payload.get("last_date") or ""),
        change_5d_pct=_float_or_none(payload.get("change_5d_pct")),
        change_20d_pct=_float_or_none(payload.get("change_20d_pct")),
        annualized_volatility_pct=_float_or_none(payload.get("annualized_volatility_pct")),
        sma_20=_float_or_none(payload.get("sma_20")),
        sma_50=_float_or_none(payload.get("sma_50")),
        support_level=_float_or_none(payload.get("support_level")),
        resistance_level=_float_or_none(payload.get("resistance_level")),
        atr_14=_float_or_none(payload.get("atr_14")),
        trend_label=str(payload.get("trend_label") or "无价格数据"),
    )


def _event_signal_from_dict(payload: Any) -> EventSignal:
    item = _mapping(payload)
    return EventSignal(
        title=str(item.get("title") or ""),
        source=str(item.get("source") or ""),
        published_at=str(item.get("published_at") or ""),
        event_scope=str(item.get("event_scope") or "公司级事件"),
        interpretation_framework=str(item.get("interpretation_framework") or ""),
        category=str(item.get("category") or "news"),
        driver=str(item.get("driver") or "技术面/期权/资金流"),
        direction=str(item.get("direction") or "中性"),
        impact_score=float(item.get("impact_score") or 0.0),
        time_window=str(item.get("time_window") or "短期"),
        surprise_level=str(item.get("surprise_level") or "未知"),
        source_reliability=float(item.get("source_reliability") or 0.0),
        evidence=str(item.get("evidence") or ""),
        impact_reason=str(item.get("impact_reason") or ""),
        counterpoint=str(item.get("counterpoint") or ""),
        quantitative_evidence=tuple(str(value) for value in _sequence(item.get("quantitative_evidence"))),
        score_breakdown=tuple(str(value) for value in _sequence(item.get("score_breakdown"))),
    )


def _scenario_forecast_from_dict(payload: Any) -> ScenarioForecast:
    item = _mapping(payload)
    return ScenarioForecast(
        name=str(item.get("name") or ""),
        horizon=str(item.get("horizon") or ""),
        price_low=_float_or_none(item.get("price_low")),
        price_high=_float_or_none(item.get("price_high")),
        rationale=str(item.get("rationale") or ""),
        trigger_conditions=tuple(str(value) for value in _sequence(item.get("trigger_conditions"))),
    )


def _data_coverage_from_dict(payload: dict[str, Any]) -> DataCoverageReport:
    return DataCoverageReport(
        coverage_level=str(payload.get("coverage_level") or "LOW"),
        confidence_cap=str(payload.get("confidence_cap") or "LOW"),
        satisfied_domains=tuple(str(value) for value in _sequence(payload.get("satisfied_domains"))),
        missing_domains=tuple(str(value) for value in _sequence(payload.get("missing_domains"))),
        gaps=tuple(_data_gap_from_dict(item) for item in _sequence(payload.get("gaps"))),
        roadmap=tuple(_roadmap_item_from_dict(item) for item in _sequence(payload.get("roadmap"))),
    )


def _data_gap_from_dict(payload: Any) -> DataGap:
    item = _mapping(payload)
    return DataGap(
        domain=str(item.get("domain") or ""),
        label=str(item.get("label") or ""),
        severity=str(item.get("severity") or ""),
        message=str(item.get("message") or ""),
        affected_drivers=tuple(str(value) for value in _sequence(item.get("affected_drivers"))),
        affected_profiles=tuple(str(value) for value in _sequence(item.get("affected_profiles"))),
        recommended_sources=tuple(str(value) for value in _sequence(item.get("recommended_sources"))),
        confidence_cap=str(item.get("confidence_cap") or "LOW"),
    )


def _roadmap_item_from_dict(payload: Any) -> DataSourceRoadmapItem:
    item = _mapping(payload)
    return DataSourceRoadmapItem(
        domain=str(item.get("domain") or ""),
        label=str(item.get("label") or ""),
        priority=str(item.get("priority") or ""),
        low_cost_sources=tuple(str(value) for value in _sequence(item.get("low_cost_sources"))),
        paid_enhancement_sources=tuple(str(value) for value in _sequence(item.get("paid_enhancement_sources"))),
        data_requirements=tuple(str(value) for value in _sequence(item.get("data_requirements"))),
        affected_drivers=tuple(str(value) for value in _sequence(item.get("affected_drivers"))),
        affected_profiles=tuple(str(value) for value in _sequence(item.get("affected_profiles"))),
        current_status=str(item.get("current_status") or ""),
    )


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("input JSON contains a non-object where an object is required")
    return value


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
