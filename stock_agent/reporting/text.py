from __future__ import annotations

import re
from typing import Any


TRAILING_PUNCTUATION = "。.;；,，、"


def join_readable_items(value: Any, *, separator: str = "、", empty: str = "无") -> str:
    """Join report snippets without producing awkward adjacent punctuation."""
    items = _list(value)
    cleaned = [_strip_trailing_punctuation(str(item).strip()) for item in items if str(item).strip()]
    if not cleaned:
        return empty
    return normalize_adjacent_punctuation(separator.join(cleaned))


def normalize_adjacent_punctuation(text: str) -> str:
    normalized = text
    replacements = {
        "。、": "、",
        ".、": "、",
        "；、": "、",
        ";、": "、",
        "，、": "、",
        ",、": "、",
        "、、": "、",
        "。。": "。",
        "，，": "，",
        "、，": "、",
        "、。": "。",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"([。；;，,、])\1+", r"\1", normalized)
    return normalized


def _strip_trailing_punctuation(text: str) -> str:
    return text.rstrip(TRAILING_PUNCTUATION).rstrip()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []
