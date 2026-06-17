"""Small helpers for duck-typed analysis inputs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


def field_value(item: Any, *names: str, default: Any = None) -> Any:
    """Return the first available attribute or mapping value from an input object."""
    if item is None:
        return default
    if isinstance(item, dict):
        for name in names:
            if name in item and item[name] is not None and item[name] != "":
                return item[name]
        return default
    for name in names:
        if hasattr(item, name):
            value = getattr(item, name)
            if value is not None and value != "":
                return value
    return default


def number(value: Any, default: float | None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    return value
