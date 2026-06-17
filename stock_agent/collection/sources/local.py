from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..config import reliability_for_source
from ..models import (
    CollectionRequest,
    FilingEvent,
    FinancialMetric,
    IndustryEvent,
    MacroPoint,
    NewsEvent,
    OfficialEvent,
    OptionData,
    PricePoint,
    ResearchReport,
    SourceRecord,
    WarningRecord,
    now_iso,
)
from ..normalization import (
    first_present,
    normalize_source_name,
    normalize_symbol,
    parse_datetime_to_iso,
    to_float_or_none,
    to_int_or_none,
)
from .base import SourceOutput


class LocalSource:
    name = "local"
    source_type = "user_uploaded_file"

    def collect(self, request: CollectionRequest) -> SourceOutput:
        output = SourceOutput()
        collected_at = now_iso()
        config = request.data_source_config.get("local", {})

        try:
            if "market_data" in request.normalized_requirements and config.get("prices_csv"):
                output.market_data.extend(read_prices_csv(Path(config["prices_csv"]), request.normalized_symbol, collected_at))
            if config.get("events_json"):
                self._load_json(Path(config["events_json"]), request, output, collected_at)
        except Exception as exc:  # noqa: BLE001
            output.warnings.append(
                WarningRecord(
                    code="local_source_failed",
                    message=f"Local source failed: {exc}",
                    source=self.name,
                    severity="ERROR",
                    collected_at=now_iso(),
                )
            )

        output.source_inventory.append(
            SourceRecord(
                name=self.name,
                source_type=self.source_type,
                enabled=True,
                used=output.records_collected > 0,
                reliability=reliability_for_source("local"),
                records_collected=output.records_collected,
                failed=bool(output.warnings),
                failure_reason="; ".join(w.message for w in output.warnings),
                collected_at=collected_at,
                raw_metadata={"config_keys": sorted(config.keys())},
            )
        )
        return output

    def _load_json(self, path: Path, request: CollectionRequest, output: SourceOutput, collected_at: str) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON list")

        for item in payload:
            if not isinstance(item, dict):
                continue
            target = _classify_json_item(item)
            if target not in request.normalized_requirements:
                continue
            if target == "filings":
                output.filings.append(_filing_from_json(item, collected_at))
            elif target == "official_events":
                output.official_events.append(_official_from_json(item, collected_at))
            elif target == "financial_metrics":
                output.financial_metrics.append(_financial_metric_from_json(item, collected_at))
            elif target == "news_events":
                output.news_events.append(_news_from_json(item, request.normalized_symbol, collected_at))
            elif target == "macro_data":
                output.macro_data.append(_macro_from_json(item, collected_at))
            elif target == "industry_data":
                output.industry_data.append(_industry_from_json(item, collected_at))
            elif target == "options_data":
                output.options_data.append(_option_from_json(item, collected_at))
            elif target == "research_reports":
                output.research_reports.append(_research_report_from_json(item, collected_at))


def read_prices_csv(path: Path, symbol: str, collected_at: str | None = None) -> list[PricePoint]:
    collected = collected_at or now_iso()
    prices: list[PricePoint] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date_time = parse_datetime_to_iso(first_present(row, "date_time", "datetime", "timestamp", "date", "time"))
            close = to_float_or_none(first_present(row, "close", "adj_close", "adjusted_close"))
            if not date_time or close is None:
                continue
            source = normalize_source_name(str(first_present(row, "source") or "local_csv"))
            reliability = reliability_for_source(source, to_float_or_none(first_present(row, "source_reliability")))
            adjusted_close = to_float_or_none(first_present(row, "adjusted_close", "adj_close"))
            prices.append(
                PricePoint(
                    date_time=date_time,
                    open=to_float_or_none(first_present(row, "open")),
                    high=to_float_or_none(first_present(row, "high")),
                    low=to_float_or_none(first_present(row, "low")),
                    close=close,
                    adjusted_close=adjusted_close,
                    volume=to_float_or_none(first_present(row, "volume")),
                    source=source,
                    source_reliability=reliability,
                    is_realtime=_truthy(first_present(row, "is_realtime")),
                    is_adjusted=adjusted_close is not None,
                    collected_at=collected,
                    raw_metadata={"row": dict(row), "symbol": normalize_symbol(symbol)},
                )
            )
    return sorted(prices, key=lambda item: item.date_time)


def _classify_json_item(item: dict[str, Any]) -> str:
    explicit = str(item.get("data_type") or item.get("type") or item.get("kind") or "").strip().lower()
    aliases = {
        "filing": "filings",
        "filings": "filings",
        "official_event": "official_events",
        "official_events": "official_events",
        "financial_metric": "financial_metrics",
        "financial_metrics": "financial_metrics",
        "news": "news_events",
        "news_event": "news_events",
        "news_events": "news_events",
        "macro": "macro_data",
        "macro_data": "macro_data",
        "industry": "industry_data",
        "industry_event": "industry_data",
        "option": "options_data",
        "options_data": "options_data",
        "research_report": "research_reports",
        "research_reports": "research_reports",
    }
    if explicit in aliases:
        return aliases[explicit]
    if item.get("filing_type") or item.get("accession_number"):
        return "filings"
    if item.get("indicator_name"):
        return "macro_data"
    if item.get("metric_name") and item.get("option_type"):
        return "options_data"
    if item.get("metric_name") and "value" in item:
        return "financial_metrics"
    if item.get("institution") or item.get("analyst"):
        return "research_reports"
    if item.get("related_company") or item.get("related_symbol") or item.get("title_or_metric"):
        return "industry_data"
    if item.get("event_type") == "official":
        return "official_events"
    return "news_events"


def _source_and_reliability(item: dict[str, Any], fallback: str = "local_json") -> tuple[str, float]:
    source = normalize_source_name(str(item.get("source") or fallback))
    reliability = reliability_for_source(source, to_float_or_none(item.get("source_reliability")))
    return source, reliability


def _news_from_json(item: dict[str, Any], symbol: str, collected_at: str) -> NewsEvent:
    source, reliability = _source_and_reliability(item)
    related = item.get("related_symbols") or [symbol]
    if isinstance(related, str):
        related = [part.strip() for part in related.split(",") if part.strip()]
    return NewsEvent(
        title=str(item.get("title", "")),
        summary_raw=str(item.get("summary_raw") or item.get("summary") or ""),
        published_at=parse_datetime_to_iso(item.get("published_at") or item.get("date")),
        url=str(item.get("url", "")),
        publisher=str(item.get("publisher", "")),
        source=source,
        source_reliability=reliability,
        event_type=str(item.get("event_type") or item.get("category") or "news"),
        related_symbols=[normalize_symbol(str(value)) for value in related],
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _filing_from_json(item: dict[str, Any], collected_at: str) -> FilingEvent:
    source, reliability = _source_and_reliability(item, "sec")
    return FilingEvent(
        filing_type=str(item.get("filing_type") or item.get("form") or ""),
        title=str(item.get("title", "")),
        filed_at=parse_datetime_to_iso(item.get("filed_at") or item.get("filing_date")),
        period_end=parse_datetime_to_iso(item.get("period_end")),
        url=str(item.get("url", "")),
        summary_raw=str(item.get("summary_raw") or item.get("summary") or ""),
        source=source,
        source_reliability=reliability,
        accession_number=str(item.get("accession_number") or item.get("accession") or ""),
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _official_from_json(item: dict[str, Any], collected_at: str) -> OfficialEvent:
    source, reliability = _source_and_reliability(item, "official")
    return OfficialEvent(
        title=str(item.get("title", "")),
        published_at=parse_datetime_to_iso(item.get("published_at") or item.get("date")),
        url=str(item.get("url", "")),
        event_type=str(item.get("event_type") or "official"),
        summary_raw=str(item.get("summary_raw") or item.get("summary") or ""),
        source=source,
        source_reliability=reliability,
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _financial_metric_from_json(item: dict[str, Any], collected_at: str) -> FinancialMetric:
    source, reliability = _source_and_reliability(item)
    return FinancialMetric(
        metric_name=str(item.get("metric_name", "")),
        value=to_float_or_none(item.get("value")),
        unit=str(item.get("unit", "")),
        period=str(item.get("period", "")),
        fiscal_year=to_int_or_none(item.get("fiscal_year")),
        fiscal_quarter=str(item.get("fiscal_quarter", "")),
        source=source,
        source_reliability=reliability,
        reported_at=parse_datetime_to_iso(item.get("reported_at")),
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _macro_from_json(item: dict[str, Any], collected_at: str) -> MacroPoint:
    source, reliability = _source_and_reliability(item, "fred")
    return MacroPoint(
        indicator_name=str(item.get("indicator_name", "")),
        value=to_float_or_none(item.get("value")),
        date=parse_datetime_to_iso(item.get("date")),
        unit=str(item.get("unit", "")),
        source=source,
        source_reliability=reliability,
        frequency=str(item.get("frequency", "")),
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _industry_from_json(item: dict[str, Any], collected_at: str) -> IndustryEvent:
    source, reliability = _source_and_reliability(item)
    return IndustryEvent(
        title_or_metric=str(item.get("title_or_metric") or item.get("title") or item.get("metric_name") or ""),
        value=to_float_or_none(item.get("value")),
        date=parse_datetime_to_iso(item.get("date")),
        related_company=str(item.get("related_company", "")),
        related_symbol=normalize_symbol(str(item.get("related_symbol", ""))),
        source=source,
        source_reliability=reliability,
        url=str(item.get("url", "")),
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _option_from_json(item: dict[str, Any], collected_at: str) -> OptionData:
    source, reliability = _source_and_reliability(item)
    return OptionData(
        metric_name=str(item.get("metric_name", "")),
        value=to_float_or_none(item.get("value")),
        date_time=parse_datetime_to_iso(item.get("date_time") or item.get("date")),
        expiration=parse_datetime_to_iso(item.get("expiration")),
        strike=to_float_or_none(item.get("strike")),
        option_type=str(item.get("option_type", "")),
        source=source,
        source_reliability=reliability,
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _research_report_from_json(item: dict[str, Any], collected_at: str) -> ResearchReport:
    source, reliability = _source_and_reliability(item, "research_report")
    return ResearchReport(
        institution=str(item.get("institution", "")),
        analyst=str(item.get("analyst", "")),
        published_at=parse_datetime_to_iso(item.get("published_at") or item.get("date")),
        rating=str(item.get("rating", "")),
        target_price=to_float_or_none(item.get("target_price")),
        summary_raw=str(item.get("summary_raw") or item.get("summary") or ""),
        key_assumptions=[str(value) for value in item.get("key_assumptions", [])],
        risks=[str(value) for value in item.get("risks", [])],
        source=source,
        source_reliability=reliability,
        file_reference=str(item.get("file_reference", "")),
        collected_at=collected_at,
        raw_metadata=dict(item),
    )


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}

