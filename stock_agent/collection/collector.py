from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Any

from .cache import GLOBAL_MEMORY_CACHE
from .config import DATA_REQUIREMENTS, REQUIREMENT_TO_RESULT_FIELD, is_enabled_source, normalize_source_key, reliability_for_source
from .dedup import deduplicate_news_events
from .models import (
    CollectionRequest,
    CollectionResult,
    CollectionSummary,
    ConflictRecord,
    IBKRStatus,
    SourceRecord,
    WarningRecord,
    now_iso,
)
from .quality import evaluate_quality
from .sources import AlphaVantageSource, FREDSource, IBKRSource, LocalSource, RSSSource, SECEdgarSource
from .sources.base import SourceOutput


SOURCE_FACTORIES = {
    "local": LocalSource,
    "alpha_vantage": AlphaVantageSource,
    "sec_edgar": SECEdgarSource,
    "fred": FREDSource,
    "rss": RSSSource,
    "ibkr": IBKRSource,
}


def collect_data(request: CollectionRequest) -> CollectionResult:
    normalized_request = _normalize_request(request)
    collection_time = now_iso()
    result = CollectionResult(
        collection_summary=CollectionSummary(
            symbol=normalized_request.normalized_symbol,
            company_name=normalized_request.company_name,
            collection_time=collection_time,
            ibkr_status=IBKRStatus(
                enabled=is_enabled_source(normalized_request.data_source_config.get("ibkr")),
                account_data_allowed=normalized_request.allow_broker_account_data,
            ),
        )
    )

    _record_disabled_sources(normalized_request, result)
    _record_unknown_requirements(normalized_request, result)

    for source_name, source_config in normalized_request.data_source_config.items():
        if not is_enabled_source(source_config):
            continue
        factory = SOURCE_FACTORIES.get(source_name)
        if factory is None:
            result.warnings.append(
                WarningRecord(
                    code="unknown_data_source",
                    message=f"Configured data source '{source_name}' is not supported and was not called.",
                    source=source_name,
                    severity="WARNING",
                    collected_at=now_iso(),
                )
            )
            continue

        source = factory()
        cached_output = _cached_source_output(normalized_request, source_name, source_config)
        if cached_output is not None:
            output = cached_output
        else:
            try:
                output = source.collect(normalized_request)
            except Exception as exc:  # noqa: BLE001
                output = SourceOutput(
                    warnings=[
                        WarningRecord(
                            code="data_source_failed",
                            message=f"{source_name} failed: {exc}",
                            source=source_name,
                            severity="ERROR",
                            collected_at=now_iso(),
                        )
                    ],
                    source_inventory=[
                        SourceRecord(
                            name=source_name,
                            source_type=getattr(source, "source_type", ""),
                            enabled=True,
                            used=False,
                            reliability=reliability_for_source(source_name),
                            records_collected=0,
                            failed=True,
                            failure_reason=str(exc),
                            collected_at=now_iso(),
                        )
                    ],
                )
            _store_source_output(normalized_request, source_name, source_config, output)
        _merge_output(result, output)
        if source_name == "ibkr":
            _update_ibkr_status(result, output)

    events_before_dedup = len(result.news_events)
    dedup_result = deduplicate_news_events(result.news_events)
    result.news_events = dedup_result.items
    result.conflicts = detect_conflicts(result)
    result.data_quality_report = evaluate_quality(normalized_request, result, dedup_result.duplicate_count)

    result.collection_summary.data_sources_used = [
        record.name for record in result.source_inventory if record.used and not record.failed
    ]
    result.collection_summary.data_sources_failed = [
        record.name for record in result.source_inventory if record.failed
    ]
    result.collection_summary.total_events_collected = events_before_dedup + len(result.official_events) + len(result.filings)
    result.collection_summary.total_events_after_dedup = len(result.news_events) + len(result.official_events) + len(result.filings)
    result.collection_summary.freshness_status = _freshness_status(result)
    result.collection_summary.overall_quality = result.data_quality_report.overall_quality
    result.collection_summary.can_generate_analysis = result.data_quality_report.can_generate_analysis
    result.collection_summary.confidence_cap = result.data_quality_report.confidence_cap
    return result


def detect_conflicts(result: CollectionResult) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    conflicts.extend(_detect_price_conflicts(result))
    conflicts.extend(_detect_financial_metric_conflicts(result))
    return conflicts


def _normalize_request(request: CollectionRequest) -> CollectionRequest:
    normalized_sources: dict[str, Any] = {}
    for source_name, source_config in request.data_source_config.items():
        key = normalize_source_key(source_name)
        config = dict(source_config or {})
        normalized_sources[key] = {**normalized_sources.get(key, {}), **config}
    normalized_requirements = [item.strip().lower() for item in request.data_requirements if item.strip()]
    return replace(
        request,
        symbol=request.normalized_symbol,
        data_requirements=normalized_requirements,
        data_source_config=normalized_sources,
    )


def _record_disabled_sources(request: CollectionRequest, result: CollectionResult) -> None:
    for source_name, source_config in request.data_source_config.items():
        if is_enabled_source(source_config):
            continue
        result.source_inventory.append(
            SourceRecord(
                name=source_name,
                source_type=getattr(SOURCE_FACTORIES.get(source_name, object), "source_type", ""),
                enabled=False,
                used=False,
                reliability=reliability_for_source(source_name),
                records_collected=0,
                collected_at=now_iso(),
            )
        )


def _record_unknown_requirements(request: CollectionRequest, result: CollectionResult) -> None:
    for requirement in request.normalized_requirements:
        if requirement not in DATA_REQUIREMENTS:
            result.warnings.append(
                WarningRecord(
                    code="unknown_data_requirement",
                    message=f"Unknown data requirement '{requirement}' was requested.",
                    source="request",
                    severity="WARNING",
                    collected_at=now_iso(),
                )
            )


def _merge_output(result: CollectionResult, output: SourceOutput) -> None:
    for field_name in REQUIREMENT_TO_RESULT_FIELD.values():
        getattr(result, field_name).extend(getattr(output, field_name))
    result.warnings.extend(output.warnings)
    result.source_inventory.extend(output.source_inventory)


def _cached_source_output(request: CollectionRequest, source_name: str, source_config: dict[str, Any]) -> SourceOutput | None:
    if not _cache_enabled(request, source_name):
        return None
    entry = GLOBAL_MEMORY_CACHE.get(_cache_key(request, source_name, source_config))
    if entry is None:
        return None
    output = copy.deepcopy(entry.value)
    _mark_output_cached(output, entry.cache_time, entry.age_seconds)
    return output


def _store_source_output(
    request: CollectionRequest,
    source_name: str,
    source_config: dict[str, Any],
    output: SourceOutput,
) -> None:
    if not _cache_enabled(request, source_name) or output.records_collected == 0:
        return
    if source_name == "ibkr" and "broker_account_data" in request.normalized_requirements:
        return
    ttl_seconds = _ttl_seconds(request, source_name)
    GLOBAL_MEMORY_CACHE.set(_cache_key(request, source_name, source_config), copy.deepcopy(output), ttl_seconds, now_iso())


def _cache_enabled(request: CollectionRequest, source_name: str) -> bool:
    if source_name == "ibkr" and "broker_account_data" in request.normalized_requirements:
        return False
    return bool(request.cache_policy.get("enabled", False))


def _ttl_seconds(request: CollectionRequest, source_name: str) -> int:
    ttl_config = request.cache_policy.get("ttl_seconds", {})
    if isinstance(ttl_config, dict) and source_name in ttl_config:
        return int(ttl_config[source_name])
    defaults = {
        "alpha_vantage": 300,
        "rss": 1800,
        "sec_edgar": 86400,
        "fred": 86400,
        "local": 86400,
        "ibkr": 60,
    }
    return int(request.cache_policy.get("default_ttl_seconds", defaults.get(source_name, 900)))


def _cache_key(request: CollectionRequest, source_name: str, source_config: dict[str, Any]) -> str:
    payload = {
        "source": source_name,
        "symbol": request.normalized_symbol,
        "market": request.market,
        "requirements": request.normalized_requirements,
        "config": _safe_cache_config(source_config),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _safe_cache_config(config: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    blocked_fragments = {"key", "token", "secret", "password", "credential", "client"}
    for key, value in config.items():
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in blocked_fragments):
            safe[key] = "<redacted>"
        elif isinstance(value, (str, int, float, bool, type(None), list, tuple, dict)):
            safe[key] = value
        else:
            safe[key] = repr(type(value))
    return safe


def _mark_output_cached(output: SourceOutput, cache_time: str, cache_age_seconds: float) -> None:
    for record in output.source_inventory:
        record.is_cached = True
        record.cache_time = cache_time
        record.cache_age_seconds = cache_age_seconds
    for field_name in REQUIREMENT_TO_RESULT_FIELD.values():
        for item in getattr(output, field_name):
            raw_metadata = dict(getattr(item, "raw_metadata", {}))
            raw_metadata.update(
                {
                    "is_cached": True,
                    "cache_time": cache_time,
                    "cache_age_seconds": cache_age_seconds,
                }
            )
            item.raw_metadata = raw_metadata


def _update_ibkr_status(result: CollectionResult, output: SourceOutput) -> None:
    status = result.collection_summary.ibkr_status
    status.enabled = True
    connected = any(record.raw_metadata.get("connected") for record in output.source_inventory)
    status.connected = connected
    status.has_realtime_permission = any(point.is_realtime and point.source.lower() == "ibkr" for point in output.market_data)
    status.has_options_permission = bool(output.options_data)
    status.market_data_type = "realtime" if status.has_realtime_permission else ("historical_or_delayed" if output.market_data else "")
    status.warnings.extend(warning.message for warning in output.warnings)


def _detect_price_conflicts(result: CollectionResult) -> list[ConflictRecord]:
    by_time: dict[str, list[Any]] = {}
    for point in result.market_data:
        if point.date_time and point.close is not None:
            by_time.setdefault(point.date_time, []).append(point)

    conflicts: list[ConflictRecord] = []
    for date_time, points in by_time.items():
        rounded_values = {round(float(point.close or 0), 4) for point in points}
        sources = {point.source for point in points}
        if len(rounded_values) <= 1 or len(sources) <= 1:
            continue
        preferred = max(points, key=lambda point: point.source_reliability)
        conflicts.append(
            ConflictRecord(
                conflict_type="market_data_price_conflict",
                conflicting_sources=[point.source for point in points],
                conflicting_values=[
                    {"date_time": point.date_time, "close": point.close, "source": point.source}
                    for point in points
                ],
                preferred_value=preferred.close,
                reason="Selected the value from the highest reliability source; requires review if material.",
                requires_review=True,
                collected_at=now_iso(),
                raw_metadata={"date_time": date_time},
            )
        )
    return conflicts


def _detect_financial_metric_conflicts(result: CollectionResult) -> list[ConflictRecord]:
    by_key: dict[tuple[str, str, int | None, str], list[Any]] = {}
    for metric in result.financial_metrics:
        if metric.value is None:
            continue
        key = (metric.metric_name.lower(), metric.period, metric.fiscal_year, metric.fiscal_quarter)
        by_key.setdefault(key, []).append(metric)

    conflicts: list[ConflictRecord] = []
    for key, metrics in by_key.items():
        rounded_values = {round(float(metric.value or 0), 4) for metric in metrics}
        sources = {metric.source for metric in metrics}
        if len(rounded_values) <= 1 or len(sources) <= 1:
            continue
        preferred = max(metrics, key=lambda metric: metric.source_reliability)
        conflicts.append(
            ConflictRecord(
                conflict_type="financial_metric_conflict",
                conflicting_sources=[metric.source for metric in metrics],
                conflicting_values=[
                    {
                        "metric_name": metric.metric_name,
                        "value": metric.value,
                        "period": metric.period,
                        "source": metric.source,
                    }
                    for metric in metrics
                ],
                preferred_value=preferred.value,
                reason="Selected the value from the highest reliability source; official filings should override secondary sources.",
                requires_review=True,
                collected_at=now_iso(),
                raw_metadata={"metric_key": key},
            )
        )
    return conflicts


def _freshness_status(result: CollectionResult) -> str:
    if not result.market_data:
        return "NO_MARKET_DATA"
    latest = max((point.date_time for point in result.market_data if point.date_time), default="")
    if not latest:
        return "UNKNOWN"
    try:
        parsed = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    except ValueError:
        return "UNKNOWN"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days
    if age_days <= 1:
        return "FRESH"
    if age_days <= 7:
        return "RECENT"
    return "STALE"
