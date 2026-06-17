from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from .models import now_iso


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip()


def normalize_source_name(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip()) or "unknown"


def parse_datetime_to_iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if not text:
        return ""

    if re.fullmatch(r"\d{8}T\d{6}", text):
        parsed = datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return parsed.isoformat()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00+00:00"

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return text


def to_float_or_none(value: Any) -> float | None:
    if value in (None, "", "None", "null", "N/A", "NA"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def to_int_or_none(value: Any) -> int | None:
    number = to_float_or_none(value)
    if number is None:
        return None
    return int(number)


def first_present(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return ""


def mask_account_id(account_id: Any) -> str:
    text = str(account_id or "").strip()
    if not text:
        return ""
    tail = text[-4:]
    return f"{'*' * max(4, len(text) - 4)}{tail}"


def metadata_with_collection(raw: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    metadata = dict(raw or {})
    metadata.update(extra)
    return metadata


def collected_now() -> str:
    return now_iso()

