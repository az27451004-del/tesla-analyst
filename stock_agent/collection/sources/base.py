from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import (
    BrokerAccountData,
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
)


@dataclass
class SourceOutput:
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
    warnings: list[WarningRecord] = field(default_factory=list)
    source_inventory: list[SourceRecord] = field(default_factory=list)

    @property
    def records_collected(self) -> int:
        return (
            len(self.market_data)
            + len(self.filings)
            + len(self.official_events)
            + len(self.financial_metrics)
            + len(self.news_events)
            + len(self.macro_data)
            + len(self.industry_data)
            + len(self.options_data)
            + len(self.broker_account_data)
            + len(self.research_reports)
        )


class CollectionSource(Protocol):
    name: str
    source_type: str

    def collect(self, request: CollectionRequest) -> SourceOutput:
        ...
