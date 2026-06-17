from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    cache_time: str
    ttl_seconds: int

    @property
    def age_seconds(self) -> float:
        cached_at = datetime.fromisoformat(self.cache_time.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - cached_at).total_seconds()

    @property
    def is_fresh(self) -> bool:
        return self.age_seconds <= self.ttl_seconds


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        entry = self._items.get(key)
        if entry is None or not entry.is_fresh:
            return None
        return entry

    def set(self, key: str, value: Any, ttl_seconds: int, cache_time: str) -> CacheEntry:
        entry = CacheEntry(value=value, ttl_seconds=ttl_seconds, cache_time=cache_time)
        self._items[key] = entry
        return entry


GLOBAL_MEMORY_CACHE = MemoryCache()

