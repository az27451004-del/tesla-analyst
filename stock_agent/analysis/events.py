"""Event-to-signal mapping for the second analysis layer."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .constants import (
    DRIVER_COMPETITION,
    DRIVER_DELIVERY,
    DRIVER_ENERGY,
    DRIVER_FUNDAMENTAL,
    DRIVER_MACRO,
    DRIVER_NARRATIVE,
    DRIVER_REGULATORY,
    DRIVER_TECHNICAL,
    DRIVER_VALUATION,
    DRIVERS,
    NEGATIVE_TERMS,
    POSITIVE_TERMS,
)
from .models import EventSignal, MarketState
from .utils import field_value, number


def build_event_signals(events: Iterable[Any]) -> tuple[EventSignal, ...]:
    signals = (_event_signal(event) for event in events)
    return tuple(sorted(signals, key=lambda item: item.impact_score, reverse=True))


def build_driver_scores(events: tuple[EventSignal, ...], market: MarketState) -> dict[str, float]:
    scores = {driver: 0.0 for driver in DRIVERS}
    for driver in DRIVERS:
        driver_events = [event for event in events if event.driver == driver][:5]
        if not driver_events:
            continue
        weighted_sum = 0.0
        weight_total = 0.0
        for index, event in enumerate(driver_events):
            signed = event.impact_score if event.direction != "负面" else -event.impact_score
            reliability_weight = 0.35 + min(1.0, max(0.0, event.source_reliability)) * 0.65
            rank_decay = 1.0 / (1.0 + index * 0.45)
            weight = reliability_weight * rank_decay
            weighted_sum += signed * weight
            weight_total += weight
        conviction = min(1.0, weight_total / 2.5)
        scores[driver] = (weighted_sum / max(weight_total, 0.001)) * conviction
    if market.last_close is not None:
        technical = 0.15
        if market.trend_label in {"多头趋势", "短中期偏强"}:
            technical = 0.35
        elif market.trend_label in {"空头趋势", "短中期偏弱"}:
            technical = -0.35
        scores[DRIVER_TECHNICAL] += technical
    return {driver: round(max(-1.0, min(1.0, value)), 3) for driver, value in scores.items()}


def _event_signal(event: Any) -> EventSignal:
    title = str(field_value(event, "title", "title_or_metric", "metric_name", default="") or "")
    summary = str(field_value(event, "summary", "summary_raw", default="") or "")
    category = str(field_value(event, "category", "event_type", "filing_type", default="news") or "news")
    text = f"{title} {summary} {category}".lower()
    sentiment = number(field_value(event, "sentiment"), _keyword_sentiment(text))
    impact = number(field_value(event, "impact_score"), 0.0)
    reliability = number(field_value(event, "source_reliability"), 0.5)
    raw_metadata = field_value(event, "raw_metadata", default={}) or {}
    driver = _driver_for_text(text, category)
    direction = "正面" if sentiment > 0.15 else "负面" if sentiment < -0.15 else "中性"
    base = _driver_base_weight(driver)
    relevance = _event_relevance(raw_metadata)
    relevance_weight = 0.45 + relevance * 0.55
    impact_score = max(impact, base + abs(sentiment) * 0.18 + reliability * 0.12)
    impact_score *= relevance_weight
    impact_score = min(_impact_cap(category, text, relevance), impact_score)
    return EventSignal(
        title=title,
        source=str(field_value(event, "source", "publisher", "institution", default="") or ""),
        category=category or "news",
        driver=driver,
        direction=direction,
        impact_score=round(impact_score, 3),
        time_window=_time_window(text),
        surprise_level="待验证" if "guidance" in text or "consensus" in text or "预期" in text else "未知",
        source_reliability=round(reliability, 3),
        evidence=summary[:240],
    )


def _driver_for_text(text: str, category: str) -> str:
    category = category.lower()
    if category in {"10-k", "10-q", "20-f", "annual report", "quarterly report", "financial_metric", "earnings"}:
        return DRIVER_FUNDAMENTAL
    if category in {"8-k", "regulatory"}:
        return DRIVER_REGULATORY
    if category in {"4", "form 4", "sc 13g", "sc 13d", "144", "filing"}:
        return DRIVER_REGULATORY
    if category in {"earnings", "financial_metric"}:
        return DRIVER_FUNDAMENTAL
    if category in {"delivery", "company_update"}:
        return DRIVER_DELIVERY
    if _has_any_phrase(text, ("fsd", "robotaxi", "autonomy", "autonomous", "ai", "ai chip", "artificial intelligence")):
        return DRIVER_NARRATIVE
    if any(term in text for term in ("earnings", "eps", "margin", "revenue", "cash flow", "guidance")):
        return DRIVER_FUNDAMENTAL
    if any(term in text for term in ("delivery", "deliveries", "inventory", "price cut", "vehicle sales")):
        return DRIVER_DELIVERY
    if category == "macro" or any(term in text for term in ("rate", "fed", "cpi", "inflation", "treasury", "dollar", "nasdaq", "vix")):
        return DRIVER_MACRO
    if any(term in text for term in ("byd", "rivian", "lucid", "ford", "gm", "competition", "market share", "price war")):
        return DRIVER_COMPETITION
    if any(term in text for term in ("sec", "recall", "lawsuit", "investigation", "regulatory", "tariff", "subsidy")):
        return DRIVER_REGULATORY
    if any(term in text for term in ("energy", "storage", "battery", "supply", "lithium", "raw material")):
        return DRIVER_ENERGY
    if any(term in text for term in ("option", "put/call", "volume", "technical", "support", "resistance", "momentum")):
        return DRIVER_TECHNICAL
    if any(term in text for term in ("valuation", "multiple", "target", "fair value", "margin of safety")):
        return DRIVER_VALUATION
    return DRIVER_TECHNICAL


def _driver_base_weight(driver: str) -> float:
    return {
        DRIVER_FUNDAMENTAL: 0.54,
        DRIVER_DELIVERY: 0.52,
        DRIVER_NARRATIVE: 0.50,
        DRIVER_MACRO: 0.48,
        DRIVER_REGULATORY: 0.50,
        DRIVER_COMPETITION: 0.44,
        DRIVER_ENERGY: 0.40,
        DRIVER_TECHNICAL: 0.42,
        DRIVER_VALUATION: 0.42,
    }.get(driver, 0.40)


def _time_window(text: str) -> str:
    if _has_any_phrase(text, ("robotaxi", "fsd", "ai", "ai chip", "artificial intelligence", "factory", "capacity", "long-term")):
        return "长期"
    if any(term in text for term in ("earnings", "guidance", "quarter", "delivery", "tariff")):
        return "中期"
    return "短期"


def _keyword_sentiment(text: str) -> float:
    positive = sum(1 for term in POSITIVE_TERMS if term in text)
    negative = sum(1 for term in NEGATIVE_TERMS if term in text)
    if positive == negative:
        return 0.0
    return max(-1.0, min(1.0, (positive - negative) / max(positive + negative, 1)))


def _has_any_phrase(text: str, terms: tuple[str, ...]) -> bool:
    return any(_phrase_matches(text, term) for term in terms)


def _phrase_matches(text: str, term: str) -> bool:
    if term == "ai":
        return re.search(r"(?<![a-z0-9])ai(?![a-z0-9])", text) is not None
    return term in text


def _event_relevance(raw_metadata: Any) -> float:
    if not isinstance(raw_metadata, dict):
        return 1.0
    relevance = raw_metadata.get("requested_symbol_relevance")
    if relevance is None:
        relevance = raw_metadata.get("symbol_relevance")
    if relevance is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(relevance)))
    except (TypeError, ValueError):
        return 1.0


def _impact_cap(category: str, text: str, relevance: float) -> float:
    normalized_category = category.lower()
    if normalized_category in {"4", "form 4", "sc 13g", "sc 13d", "144"}:
        return 0.38
    if normalized_category in {"10-k", "10-q", "8-k", "filing"}:
        return 0.62
    if relevance < 0.75:
        return 0.55
    if "raw sec filing metadata collected" in text:
        return 0.48
    return 1.0
