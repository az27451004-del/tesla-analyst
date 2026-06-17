from __future__ import annotations

import argparse
from pathlib import Path

from stock_agent.analysis import analyze_market_events
from stock_agent.decision import build_decision_plan
from tsla_agent.config import AgentConfig
from tsla_agent.connectors import AlphaVantageConnector, LocalDataConnector, RSSConnector, SECConnector
from tsla_agent.connectors.base import CollectionResult
from tsla_agent.forecast import forecast_price_path, summarize_market, weighted_event_sentiment
from tsla_agent.llm import summarize_with_llm
from tsla_agent.report import build_markdown_report, write_report
from tsla_agent.scoring import score_events


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AgentConfig(symbol=args.symbol, max_events=args.max_events)

    result = CollectionResult()
    local_prices = Path(args.prices_csv) if args.prices_csv else None
    local_events = Path(args.events_json) if args.events_json else None
    if args.sample_data:
        local_prices = config.data_dir / "sample_prices.csv"
        local_events = config.data_dir / "sample_events.json"

    if local_prices or local_events:
        result.extend(LocalDataConnector(local_prices, local_events).collect(config))

    if not args.offline:
        for connector in (AlphaVantageConnector(), SECConnector(), RSSConnector()):
            result.extend(connector.collect(config))

    events = score_events(result.events)[: config.max_events]
    market = summarize_market(config.normalized_symbol, result.prices)
    sentiment_tilt = weighted_event_sentiment(events)
    forecast = forecast_price_path(result.prices, sentiment_tilt, config.forecast_horizons)
    analysis = analyze_market_events(
        symbol=config.normalized_symbol,
        prices=result.prices,
        events=events,
        warnings=result.warnings,
        missing_requirements=["macro_data", "financial_metrics", "industry_data", "options_data"],
        official_events_count=sum(1 for event in events if event.source.upper() == "SEC"),
        has_backtest=False,
    )
    decision_plan = None
    if args.include_decision_plan:
        decision_plan = build_decision_plan(analysis, args.investor_type, args.horizon)

    llm_summary = None
    if not args.no_llm and not args.offline:
        try:
            llm_summary = summarize_with_llm(events, market, forecast)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"LLM 总结失败，已使用本地摘要：{exc}")

    report = build_markdown_report(
        market,
        events,
        forecast,
        result.warnings,
        llm_summary,
        analysis=analysis,
        decision_plan=decision_plan,
    )
    output = Path(args.output) if args.output else config.report_dir / f"{config.normalized_symbol.lower()}_report.md"
    write_report(report, output)
    print(f"Report written to {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tesla stock analysis agent")
    parser.add_argument("--symbol", default="TSLA", help="Ticker symbol, default: TSLA")
    parser.add_argument("--offline", action="store_true", help="Do not call remote data sources")
    parser.add_argument("--sample-data", action="store_true", help="Use bundled fictional sample data")
    parser.add_argument("--prices-csv", help="Local price CSV with date and close columns")
    parser.add_argument("--events-json", help="Local event JSON list")
    parser.add_argument("--output", help="Markdown report output path")
    parser.add_argument("--max-events", type=int, default=30, help="Maximum events to include")
    parser.add_argument("--no-llm", action="store_true", help="Disable optional LLM summary")
    parser.add_argument("--include-decision-plan", action="store_true", help="Include third-layer conditional decision plan")
    parser.add_argument("--investor-type", default="long_term_fundamental", help="Investor profile for decision plan")
    parser.add_argument("--horizon", default="", help="Investment or trading horizon for decision plan")
    return parser
