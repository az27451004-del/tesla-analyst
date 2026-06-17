from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class CollectionRequest:
    symbol: str
    market: str = "US"
    company_name: str = ""
    data_requirements: list[str] = field(default_factory=list)
    allow_realtime: bool = False
    allow_paid_sources: bool = False
    allow_web_search: bool = False
    allow_social_media: bool = False
    allow_broker_account_data: bool = False
    allow_positions_pnl: bool = False
    data_source_config: dict[str, Any] = field(default_factory=dict)
    broker_config: dict[str, Any] = field(default_factory=dict)
    cache_policy: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_symbol(self) -> str:
        return self.symbol.upper().strip()

    @property
    def normalized_requirements(self) -> list[str]:
        return [item.strip().lower() for item in self.data_requirements if item.strip()]


@dataclass
class PricePoint:
    date_time: str = ""
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adjusted_close: float | None = None
    volume: float | None = None
    source: str = ""
    source_reliability: float = 0.0
    is_realtime: bool = False
    is_adjusted: bool = False
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FilingEvent:
    filing_type: str = ""
    title: str = ""
    filed_at: str = ""
    period_end: str = ""
    url: str = ""
    summary_raw: str = ""
    source: str = ""
    source_reliability: float = 0.0
    accession_number: str = ""
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OfficialEvent:
    title: str = ""
    published_at: str = ""
    url: str = ""
    event_type: str = ""
    summary_raw: str = ""
    source: str = ""
    source_reliability: float = 0.0
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FinancialMetric:
    metric_name: str = ""
    value: float | None = None
    unit: str = ""
    period: str = ""
    fiscal_year: int | None = None
    fiscal_quarter: str = ""
    source: str = ""
    source_reliability: float = 0.0
    reported_at: str = ""
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NewsEvent:
    title: str = ""
    summary_raw: str = ""
    published_at: str = ""
    url: str = ""
    publisher: str = ""
    source: str = ""
    source_reliability: float = 0.0
    event_type: str = "news"
    related_symbols: list[str] = field(default_factory=list)
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MacroPoint:
    indicator_name: str = ""
    value: float | None = None
    date: str = ""
    unit: str = ""
    source: str = ""
    source_reliability: float = 0.0
    frequency: str = ""
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IndustryEvent:
    title_or_metric: str = ""
    value: float | None = None
    date: str = ""
    related_company: str = ""
    related_symbol: str = ""
    source: str = ""
    source_reliability: float = 0.0
    url: str = ""
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptionData:
    metric_name: str = ""
    value: float | None = None
    date_time: str = ""
    expiration: str = ""
    strike: float | None = None
    option_type: str = ""
    source: str = ""
    source_reliability: float = 0.0
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerPosition:
    symbol: str = ""
    quantity: float | None = None
    average_cost: float | None = None
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    currency: str = ""
    source: str = "ibkr"


@dataclass
class BrokerAccountData:
    account_id_masked: str = ""
    currency: str = ""
    net_liquidation: float | None = None
    cash_balance: float | None = None
    margin_requirement: float | None = None
    positions: list[BrokerPosition] = field(default_factory=list)
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    source: str = ""
    source_reliability: float = 0.0
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchReport:
    institution: str = ""
    analyst: str = ""
    published_at: str = ""
    rating: str = ""
    target_price: float | None = None
    summary_raw: str = ""
    key_assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    source: str = ""
    source_reliability: float = 0.0
    file_reference: str = ""
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceRecord:
    name: str = ""
    source_type: str = ""
    enabled: bool = False
    used: bool = False
    reliability: float = 0.0
    records_collected: int = 0
    failed: bool = False
    failure_reason: str = ""
    is_cached: bool = False
    cache_time: str = ""
    cache_age_seconds: float | None = None
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictRecord:
    conflict_type: str = ""
    conflicting_sources: list[str] = field(default_factory=list)
    conflicting_values: list[Any] = field(default_factory=list)
    preferred_value: Any = None
    reason: str = ""
    requires_review: bool = True
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WarningRecord:
    code: str = ""
    message: str = ""
    source: str = ""
    severity: str = "WARNING"
    collected_at: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataQualityReport:
    overall_quality: str = "INSUFFICIENT"
    can_generate_analysis: bool = False
    confidence_cap: str = "LOW"
    missing_requirements: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)


@dataclass
class IBKRStatus:
    enabled: bool = False
    connected: bool = False
    market_data_type: str = ""
    has_realtime_permission: bool = False
    has_options_permission: bool = False
    account_data_allowed: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class CollectionSummary:
    symbol: str = ""
    company_name: str = ""
    collection_time: str = ""
    data_sources_used: list[str] = field(default_factory=list)
    data_sources_failed: list[str] = field(default_factory=list)
    total_events_collected: int = 0
    total_events_after_dedup: int = 0
    freshness_status: str = "UNKNOWN"
    overall_quality: str = "INSUFFICIENT"
    can_generate_analysis: bool = False
    confidence_cap: str = "LOW"
    ibkr_status: IBKRStatus = field(default_factory=IBKRStatus)


@dataclass
class CollectionResult:
    collection_summary: CollectionSummary = field(default_factory=CollectionSummary)
    market_data: list[PricePoint] = field(default_factory=list)
    filings: list[FilingEvent] = field(default_factory=list)
    official_events: list[OfficialEvent] = field(default_factory=list)
    financial_metrics: list[FinancialMetric] = field(default_factory=list)
    news_events: list[NewsEvent] = field(default_factory=list)
    macro_data: list[MacroPoint] = field(default_factory=list)
    industry_data: list[IndustryEvent] = field(default_factory=list)
    options_data: list[OptionData] = field(default_factory=list)
    broker_account_data: list[BrokerAccountData] = field(default_factory=list)
    research_reports: list[ResearchReport] = field(default_factory=list)
    source_inventory: list[SourceRecord] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    warnings: list[WarningRecord] = field(default_factory=list)
    data_quality_report: DataQualityReport = field(default_factory=DataQualityReport)

    def to_dict(self) -> dict[str, Any]:
        return to_plain(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    return value

