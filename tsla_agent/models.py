from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PricePoint:
    date: str
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None


@dataclass(frozen=True)
class Event:
    source: str
    title: str
    summary: str = ""
    url: str = ""
    published_at: str = ""
    category: str = "news"
    sentiment: float = 0.0
    impact_score: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketSummary:
    symbol: str
    last_close: float | None
    last_date: str
    change_5d_pct: float | None
    change_20d_pct: float | None
    annualized_volatility_pct: float | None
    sma_20: float | None
    sma_50: float | None
    trend_label: str


@dataclass(frozen=True)
class ForecastPoint:
    horizon_days: int
    base_price: float
    bull_price: float
    bear_price: float
    expected_return_pct: float
    confidence_band_pct: float


@dataclass(frozen=True)
class ForecastResult:
    signal: str
    rationale: str
    points: tuple[ForecastPoint, ...]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "source": event.source,
        "title": event.title,
        "summary": event.summary,
        "url": event.url,
        "published_at": event.published_at,
        "category": event.category,
        "sentiment": event.sentiment,
        "impact_score": event.impact_score,
        "tags": list(event.tags),
    }
