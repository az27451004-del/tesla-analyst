from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from tsla_agent.config import AgentConfig
from tsla_agent.connectors.base import CollectionResult
from tsla_agent.models import Event, PricePoint


class LocalDataConnector:
    name = "local"

    def __init__(self, prices_csv: Path | None = None, events_json: Path | None = None):
        self.prices_csv = prices_csv
        self.events_json = events_json

    def collect(self, config: AgentConfig) -> CollectionResult:
        result = CollectionResult()
        if self.prices_csv:
            result.prices.extend(read_prices_csv(self.prices_csv))
        if self.events_json:
            result.events.extend(read_events_json(self.events_json))
        return result


def read_prices_csv(path: Path) -> list[PricePoint]:
    prices: list[PricePoint] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date = _first(row, "date", "timestamp", "time")
            close = _float_or_none(_first(row, "close", "adj_close", "adjusted_close"))
            if not date or close is None:
                continue
            prices.append(
                PricePoint(
                    date=date,
                    close=close,
                    open=_float_or_none(_first(row, "open")),
                    high=_float_or_none(_first(row, "high")),
                    low=_float_or_none(_first(row, "low")),
                    volume=_float_or_none(_first(row, "volume")),
                )
            )
    return sorted(prices, key=lambda item: item.date)


def read_events_json(path: Path) -> list[Event]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON list")
    events: list[Event] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        events.append(
            Event(
                source=str(item.get("source", "local")),
                title=str(item["title"]),
                summary=str(item.get("summary", "")),
                url=str(item.get("url", "")),
                published_at=str(item.get("published_at", "")),
                category=str(item.get("category", "news")),
                sentiment=float(item.get("sentiment", 0.0) or 0.0),
                impact_score=float(item.get("impact_score", 0.0) or 0.0),
                tags=tuple(str(tag) for tag in item.get("tags", [])),
                raw=dict(item),
            )
        )
    return events


def _first(row: dict[str, Any], *keys: str) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _float_or_none(value: str) -> float | None:
    if value in ("", "None", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
