from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import REQUIREMENT_TO_RESULT_FIELD, reliability_for_source
from .models import CollectionRequest, CollectionResult, DataQualityReport, WarningRecord, now_iso


def evaluate_quality(request: CollectionRequest, result: CollectionResult, duplicate_count: int = 0) -> DataQualityReport:
    missing_requirements = _missing_requirements(request, result)
    warning_messages = [warning.message for warning in result.warnings]
    checks: dict[str, Any] = {
        "requirements_requested": request.normalized_requirements,
        "requirements_missing": missing_requirements,
        "has_market_data": bool(result.market_data),
        "has_volume": any(point.volume is not None for point in result.market_data),
        "has_filings": bool(result.filings),
        "has_macro_data": bool(result.macro_data),
        "has_news_events": bool(result.news_events),
        "conflict_count": len(result.conflicts),
        "duplicate_event_count": duplicate_count,
        "low_reliability_record_count": _low_reliability_count(result),
        "unknown_source_count": _unknown_source_count(result),
        "sample_data_detected": _has_sample_data(result),
        "market_data_stale": _market_data_stale(result),
        "ibkr_enabled": result.collection_summary.ibkr_status.enabled,
        "ibkr_connected": result.collection_summary.ibkr_status.connected,
        "broker_account_data_allowed": request.allow_broker_account_data,
        "positions_pnl_allowed": request.allow_positions_pnl,
    }

    if not request.normalized_requirements:
        _append_warning(result, "missing_data_requirements", "No data_requirements were provided.", "request", "ERROR")

    if "market_data" in request.normalized_requirements and not result.market_data:
        _append_warning(result, "missing_market_data", "Requested market_data but no market data was collected.", "quality", "ERROR")

    if result.market_data and not checks["has_volume"]:
        _append_warning(result, "missing_volume", "Market data is missing volume values.", "quality", "WARNING")

    if checks["sample_data_detected"]:
        _append_warning(result, "sample_data_detected", "Sample or fictional data was detected and must not be used as real analysis input.", "quality", "WARNING")

    if checks["market_data_stale"]:
        _append_warning(result, "stale_market_data", "Latest market data appears stale.", "quality", "WARNING")

    if result.conflicts:
        _append_warning(result, "conflicts_detected", "Conflicting data points were detected and require review.", "quality", "WARNING")

    if duplicate_count:
        _append_warning(result, "duplicates_merged", f"{duplicate_count} duplicate news events were merged.", "quality", "INFO")

    warning_messages = [warning.message for warning in result.warnings]
    total_records = _total_records(result)
    all_requested_missing = bool(request.normalized_requirements) and len(missing_requirements) >= len(request.normalized_requirements)

    if not request.normalized_requirements or total_records == 0 or all_requested_missing:
        overall_quality = "INSUFFICIENT"
        can_generate_analysis = False
        confidence_cap = "LOW"
    elif missing_requirements or result.conflicts or checks["sample_data_detected"]:
        overall_quality = "LOW"
        can_generate_analysis = "market_data" not in missing_requirements
        confidence_cap = "LOW"
    elif result.warnings or checks["low_reliability_record_count"]:
        overall_quality = "MEDIUM"
        can_generate_analysis = True
        confidence_cap = "MEDIUM"
    else:
        overall_quality = "HIGH"
        can_generate_analysis = True
        confidence_cap = "HIGH"

    return DataQualityReport(
        overall_quality=overall_quality,
        can_generate_analysis=can_generate_analysis,
        confidence_cap=confidence_cap,
        missing_requirements=missing_requirements,
        warnings=warning_messages,
        checks=checks,
    )


def _missing_requirements(request: CollectionRequest, result: CollectionResult) -> list[str]:
    missing: list[str] = []
    if not request.normalized_requirements:
        return ["data_requirements"]
    for requirement in request.normalized_requirements:
        field_name = REQUIREMENT_TO_RESULT_FIELD.get(requirement)
        if not field_name:
            missing.append(requirement)
            continue
        if not getattr(result, field_name):
            missing.append(requirement)
    return missing


def _append_warning(result: CollectionResult, code: str, message: str, source: str, severity: str) -> None:
    if any(warning.code == code and warning.message == message for warning in result.warnings):
        return
    result.warnings.append(
        WarningRecord(code=code, message=message, source=source, severity=severity, collected_at=now_iso())
    )


def _iter_records(result: CollectionResult):
    for field_name in REQUIREMENT_TO_RESULT_FIELD.values():
        for item in getattr(result, field_name):
            yield item


def _low_reliability_count(result: CollectionResult) -> int:
    return sum(1 for item in _iter_records(result) if getattr(item, "source_reliability", 1.0) < 0.5)


def _unknown_source_count(result: CollectionResult) -> int:
    count = 0
    for item in _iter_records(result):
        source = getattr(item, "source", "")
        if reliability_for_source(source) <= 0.30:
            count += 1
    return count


def _has_sample_data(result: CollectionResult) -> bool:
    for item in _iter_records(result):
        source = str(getattr(item, "source", "")).lower()
        metadata = str(getattr(item, "raw_metadata", {})).lower()
        if "sample" in source or "sample" in metadata or "fictional" in metadata or "example.com" in metadata:
            return True
    return False


def _market_data_stale(result: CollectionResult) -> bool:
    if not result.market_data:
        return False
    latest = max((point.date_time for point in result.market_data if point.date_time), default="")
    if not latest:
        return True
    try:
        parsed = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days > 7


def _total_records(result: CollectionResult) -> int:
    return sum(len(getattr(result, field_name)) for field_name in REQUIREMENT_TO_RESULT_FIELD.values())

