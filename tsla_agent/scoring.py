from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from tsla_agent.models import Event


POSITIVE_TERMS = {
    "beat",
    "beats",
    "record",
    "upgrade",
    "raised target",
    "margin improvement",
    "strong demand",
    "approval",
    "expansion",
    "delivery growth",
    "cash flow",
    "profit",
    "profitable",
}

NEGATIVE_TERMS = {
    "miss",
    "misses",
    "downgrade",
    "recall",
    "investigation",
    "lawsuit",
    "margin pressure",
    "price cut",
    "weak demand",
    "delay",
    "production halt",
    "regulatory probe",
    "tariff",
    "loss",
}

CATEGORY_WEIGHT = {
    "earnings": 0.95,
    "delivery": 0.9,
    "company_update": 0.82,
    "regulatory": 0.8,
    "filing": 0.7,
    "macro": 0.7,
    "competition": 0.65,
    "insider": 0.55,
    "news": 0.5,
}


def score_events(events: list[Event], now: datetime | None = None) -> list[Event]:
    scored = [score_event(event, now=now) for event in events]
    return sorted(scored, key=lambda item: (item.impact_score, abs(item.sentiment)), reverse=True)


def score_event(event: Event, now: datetime | None = None) -> Event:
    now = now or datetime.now(timezone.utc)
    text = f"{event.title} {event.summary}".lower()
    sentiment = event.sentiment or keyword_sentiment(text)
    category = infer_category(event.category, text)
    base = CATEGORY_WEIGHT.get(category, CATEGORY_WEIGHT["news"])
    recency = recency_factor(event.published_at, now)
    event_magnitude = magnitude_factor(text)
    impact = min(1.0, max(event.impact_score, base * recency + event_magnitude + abs(sentiment) * 0.12))
    return replace(
        event,
        category=category,
        sentiment=round(max(-1.0, min(1.0, sentiment)), 3),
        impact_score=round(impact, 3),
    )


def keyword_sentiment(text: str) -> float:
    positive_hits = sum(1 for term in POSITIVE_TERMS if term in text)
    negative_hits = sum(1 for term in NEGATIVE_TERMS if term in text)
    if positive_hits == negative_hits:
        return 0.0
    score = (positive_hits - negative_hits) / max(positive_hits + negative_hits, 1)
    return max(-1.0, min(1.0, score))


def infer_category(current: str, text: str) -> str:
    if current and current != "news":
        return current
    if any(term in text for term in ("delivery", "deliveries", "vehicle sales")):
        return "delivery"
    if any(term in text for term in ("earnings", "eps", "revenue", "margin", "cash flow")):
        return "earnings"
    if any(term in text for term in ("sec", "filing", "10-k", "10-q", "8-k")):
        return "filing"
    if any(term in text for term in ("recall", "nhtsa", "investigation", "lawsuit", "regulatory")):
        return "regulatory"
    if any(term in text for term in ("rate", "fed", "cpi", "inflation", "treasury", "dollar")):
        return "macro"
    if any(term in text for term in ("byd", "rivian", "lucid", "gm", "ford", "competition")):
        return "competition"
    return current or "news"


def recency_factor(value: str, now: datetime) -> float:
    published = parse_datetime(value)
    if not published:
        return 0.75
    age_days = max((now - published).total_seconds() / 86400, 0)
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.88
    if age_days <= 30:
        return 0.72
    if age_days <= 90:
        return 0.45
    return 0.25


def magnitude_factor(text: str) -> float:
    high_impact = ("recall", "investigation", "earnings", "deliveries", "guidance", "tariff", "rate cut", "rate hike")
    if any(term in text for term in high_impact):
        return 0.12
    return 0.0


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
