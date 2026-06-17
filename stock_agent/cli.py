from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collection import CollectionRequest, collect_data
from .collection.inspection import build_collection_audit_markdown


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "collect":
        request = _build_collection_request(args)
        result = collect_data(request)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.to_json(indent=2), encoding="utf-8")
        print(f"Collection result written to {output}")
        return 0

    if args.command == "inspect":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = build_collection_audit_markdown(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"Collection audit written to {output}")
        return 0

    if args.command == "decide":
        from .decision.cli import build_decision_output

        content, _, _ = build_decision_output(
            input_path=Path(args.input),
            investor_type=args.investor_type,
            horizon=args.horizon,
            output_format=args.format,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"Decision plan written to {output}")
        return 0

    if args.command == "layer12-report":
        from .analysis.report import write_layer12_test_outputs

        validation = write_layer12_test_outputs(
            collection_input=Path(args.collection_input),
            analysis_output=Path(args.analysis_output),
            report_output=Path(args.report_output),
            validation_output=Path(args.validation_output) if args.validation_output else None,
        )
        print(f"Layer 1/2 report written to {args.report_output}")
        print(f"Layer 1/2 status: {validation['status']}")
        return 0

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock agent utilities")
    subparsers = parser.add_subparsers(dest="command")

    collect = subparsers.add_parser("collect", description="Run the independent information collection layer")
    collect.add_argument("--symbol", required=True)
    collect.add_argument("--market", default="US")
    collect.add_argument("--company-name", default="")
    collect.add_argument("--requirements", required=True, help="Comma separated data requirements")
    collect.add_argument("--output", required=True)
    collect.add_argument("--prices-csv")
    collect.add_argument("--events-json")
    collect.add_argument("--enable-alpha-vantage", action="store_true")
    collect.add_argument("--enable-sec", action="store_true")
    collect.add_argument("--sec-cik")
    collect.add_argument("--enable-fred", action="store_true")
    collect.add_argument("--rss-url", action="append", default=[])
    collect.add_argument("--rss-symbols", help="Comma separated symbols for generated RSS feeds, e.g. TSLA,AAPL,NVDA")
    collect.add_argument(
        "--rss-alias",
        action="append",
        default=[],
        help="RSS symbol aliases in SYMBOL=alias1|alias2 format. Can be repeated.",
    )
    collect.add_argument("--enable-ibkr", action="store_true")
    collect.add_argument("--allow-realtime", action="store_true")
    collect.add_argument("--allow-paid-sources", action="store_true")
    collect.add_argument("--allow-web-search", action="store_true")
    collect.add_argument("--allow-social-media", action="store_true")
    collect.add_argument("--allow-broker-account-data", action="store_true")
    collect.add_argument("--allow-positions-pnl", action="store_true")

    inspect = subparsers.add_parser("inspect", description="Render a CollectionResult JSON file as a Markdown audit report")
    inspect.add_argument("--input", required=True, help="CollectionResult JSON input path")
    inspect.add_argument("--output", required=True, help="Markdown audit report output path")

    decide = subparsers.add_parser("decide", description="Run the independent third decision expression layer")
    decide.add_argument("--input", required=True, help="AnalysisResult JSON input path")
    decide.add_argument("--output", required=True, help="DecisionPlan output path")
    decide.add_argument("--format", choices=("json", "markdown"), default="json", help="Output format")
    decide.add_argument("--investor-type", default="long_term_fundamental", help="Investor profile for decision plan")
    decide.add_argument("--horizon", default="", help="Investment or trading horizon for decision plan")

    layer12 = subparsers.add_parser("layer12-report", description="Analyze a CollectionResult and write a Chinese layer 1/2 test report")
    layer12.add_argument("--collection-input", required=True, help="CollectionResult JSON input path")
    layer12.add_argument("--analysis-output", required=True, help="AnalysisResult JSON output path")
    layer12.add_argument("--report-output", required=True, help="Chinese Markdown report output path")
    layer12.add_argument("--validation-output", help="Optional validation JSON output path")
    return parser


def _build_collection_request(args: argparse.Namespace) -> CollectionRequest:
    data_source_config = {}
    if args.prices_csv or args.events_json:
        data_source_config["local"] = {
            "enabled": True,
            "prices_csv": args.prices_csv,
            "events_json": args.events_json,
        }
    if args.enable_alpha_vantage:
        data_source_config["alpha_vantage"] = {"enabled": True}
    if args.enable_sec:
        sec_config = {"enabled": True}
        if args.sec_cik:
            sec_config["cik"] = args.sec_cik
        data_source_config["sec_edgar"] = sec_config
    if args.enable_fred:
        data_source_config["fred"] = {"enabled": True}
    if args.rss_url or args.rss_symbols or args.rss_alias:
        rss_config = {"enabled": True}
        if args.rss_url:
            rss_config["urls"] = args.rss_url
        if args.rss_symbols:
            rss_config["symbols"] = _split_csv(args.rss_symbols)
        if args.rss_alias:
            rss_config["company_aliases"] = _parse_rss_aliases(args.rss_alias)
        data_source_config["rss"] = rss_config
    if args.enable_ibkr:
        data_source_config["ibkr"] = {"enabled": True}

    return CollectionRequest(
        symbol=args.symbol,
        market=args.market,
        company_name=args.company_name,
        data_requirements=[item.strip() for item in args.requirements.split(",") if item.strip()],
        allow_realtime=args.allow_realtime,
        allow_paid_sources=args.allow_paid_sources,
        allow_web_search=args.allow_web_search,
        allow_social_media=args.allow_social_media,
        allow_broker_account_data=args.allow_broker_account_data,
        allow_positions_pnl=args.allow_positions_pnl,
        data_source_config=data_source_config,
    )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_rss_aliases(values: list[str]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for value in values:
        if "=" not in value:
            continue
        raw_symbol, raw_aliases = value.split("=", 1)
        symbol = raw_symbol.upper().strip()
        if not symbol:
            continue
        aliases.setdefault(symbol, [])
        for alias in raw_aliases.split("|"):
            cleaned = alias.strip()
            if cleaned and cleaned not in aliases[symbol]:
                aliases[symbol].append(cleaned)
    return aliases


if __name__ == "__main__":
    raise SystemExit(main())
