from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from ..config import DEFAULT_FRED_SERIES, reliability_for_source
from ..models import CollectionRequest, MacroPoint, SourceRecord, WarningRecord, now_iso
from ..normalization import parse_datetime_to_iso, to_float_or_none
from .base import SourceOutput


class FREDSource:
    name = "fred"
    source_type = "government_macro_api"

    def collect(self, request: CollectionRequest) -> SourceOutput:
        output = SourceOutput()
        collected_at = now_iso()
        config = request.data_source_config.get(self.name, {})

        if "macro_data" not in request.normalized_requirements:
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        api_key = config.get("api_key") or os.getenv("FRED_API_KEY")
        if not api_key:
            output.warnings.append(_warning("fred_api_key_missing", "FRED_API_KEY is missing.", self.name))
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        series = config.get("series") or DEFAULT_FRED_SERIES
        for indicator_name, series_id in series.items():
            try:
                output.macro_data.extend(self._fetch_series(str(indicator_name), str(series_id), str(api_key), collected_at))
            except Exception as exc:  # noqa: BLE001
                output.warnings.append(_warning("fred_series_failed", f"FRED series {series_id} failed: {exc}", self.name))

        output.source_inventory.append(self._source_record(output, collected_at))
        return output

    def _fetch_series(self, indicator_name: str, series_id: str, api_key: str, collected_at: str) -> list[MacroPoint]:
        params = urllib.parse.urlencode(
            {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": "1",
            }
        )
        request = urllib.request.Request(
            f"https://api.stlouisfed.org/fred/series/observations?{params}",
            headers={"User-Agent": "stock-agent-collector/0.1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        points: list[MacroPoint] = []
        for item in payload.get("observations", []):
            value = to_float_or_none(item.get("value"))
            if value is None:
                continue
            points.append(
                MacroPoint(
                    indicator_name=indicator_name,
                    value=value,
                    date=parse_datetime_to_iso(item.get("date")),
                    unit=str(item.get("unit", "")),
                    source="FRED",
                    source_reliability=reliability_for_source("FRED"),
                    frequency=str(item.get("frequency", "")),
                    collected_at=collected_at,
                    raw_metadata={"series_id": series_id, "observation": item},
                )
            )
        return points

    def _source_record(self, output: SourceOutput, collected_at: str) -> SourceRecord:
        return SourceRecord(
            name=self.name,
            source_type=self.source_type,
            enabled=True,
            used=output.records_collected > 0,
            reliability=reliability_for_source("FRED"),
            records_collected=output.records_collected,
            failed=bool(output.warnings) and output.records_collected == 0,
            failure_reason="; ".join(w.message for w in output.warnings),
            collected_at=collected_at,
        )


def _warning(code: str, message: str, source: str) -> WarningRecord:
    return WarningRecord(code=code, message=message, source=source, severity="WARNING", collected_at=now_iso())

