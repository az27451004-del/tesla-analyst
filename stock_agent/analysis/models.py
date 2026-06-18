"""Public data models returned by the analysis layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stock_agent.data_coverage import DataCoverageReport

from .constants import DRIVER_TECHNICAL
from .utils import to_plain


@dataclass(frozen=True)
class MarketState:
    symbol: str
    last_close: float | None = None
    last_date: str = ""
    change_5d_pct: float | None = None
    change_20d_pct: float | None = None
    annualized_volatility_pct: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    support_level: float | None = None
    resistance_level: float | None = None
    atr_14: float | None = None
    trend_label: str = "无价格数据"


@dataclass(frozen=True)
class EventSignal:
    title: str
    source: str = ""
    category: str = "news"
    driver: str = DRIVER_TECHNICAL
    direction: str = "中性"
    impact_score: float = 0.0
    time_window: str = "短期"
    surprise_level: str = "未知"
    source_reliability: float = 0.0
    evidence: str = ""
    impact_reason: str = ""
    counterpoint: str = ""
    quantitative_evidence: tuple[str, ...] = field(default_factory=tuple)
    score_breakdown: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioForecast:
    name: str
    horizon: str
    price_low: float | None
    price_high: float | None
    rationale: str
    trigger_conditions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AnalysisResult:
    symbol: str
    generated_at: str
    market_state: MarketState
    event_signals: tuple[EventSignal, ...]
    driver_scores: dict[str, float]
    scenario_forecasts: tuple[ScenarioForecast, ...]
    quality_downgrades: tuple[str, ...]
    confidence_level: str
    data_coverage: DataCoverageReport

    def to_dict(self) -> dict[str, Any]:
        return to_plain(self)
