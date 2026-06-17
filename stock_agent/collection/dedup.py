from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .models import NewsEvent


@dataclass
class DedupResult:
    items: list[NewsEvent]
    duplicate_count: int = 0


def deduplicate_news_events(events: list[NewsEvent]) -> DedupResult:
    deduped: list[NewsEvent] = []
    duplicate_count = 0

    for event in events:
        match_index = _find_duplicate(deduped, event)
        if match_index is None:
            event.raw_metadata = _with_dedup_metadata(event, [event], event)
            deduped.append(event)
            continue

        duplicate_count += 1
        existing = deduped[match_index]
        merged_members = list(existing.raw_metadata.get("dedup", {}).get("merged_records", []))
        if not merged_members:
            merged_members = [existing.raw_metadata]
        merged_members.append(event.raw_metadata)

        primary = max([existing, event], key=lambda item: item.source_reliability)
        merged = NewsEvent(
            title=primary.title or existing.title or event.title,
            summary_raw=primary.summary_raw or existing.summary_raw or event.summary_raw,
            published_at=primary.published_at or existing.published_at or event.published_at,
            url=primary.url or existing.url or event.url,
            publisher=primary.publisher or existing.publisher or event.publisher,
            source=primary.source,
            source_reliability=primary.source_reliability,
            event_type=primary.event_type or existing.event_type or event.event_type,
            related_symbols=sorted(set(existing.related_symbols + event.related_symbols)),
            collected_at=primary.collected_at or existing.collected_at or event.collected_at,
            raw_metadata=_with_dedup_metadata(primary, [existing, event], primary, merged_members),
        )
        deduped[match_index] = merged

    return DedupResult(items=deduped, duplicate_count=duplicate_count)


def _find_duplicate(events: list[NewsEvent], candidate: NewsEvent) -> int | None:
    for index, event in enumerate(events):
        if candidate.url and event.url and candidate.url.strip().lower() == event.url.strip().lower():
            return index
        if _same_day(event.published_at, candidate.published_at) and _title_similarity(event.title, candidate.title) >= 0.88:
            return index
    return None


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_title(left), _normalize_title(right)).ratio()


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()


def _same_day(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left[:10] == right[:10]


def _with_dedup_metadata(
    primary: NewsEvent,
    members: list[NewsEvent],
    event_for_raw: NewsEvent,
    merged_records: list[dict] | None = None,
) -> dict:
    all_sources: list[str] = []
    for member in members:
        if member.source and member.source not in all_sources:
            all_sources.append(member.source)
    raw = dict(event_for_raw.raw_metadata)
    raw["dedup"] = {
        "primary_source": primary.source,
        "all_sources": all_sources,
        "highest_source_reliability": primary.source_reliability,
        "source_count": len(all_sources),
        "merged_records": merged_records or [member.raw_metadata for member in members],
    }
    return raw

