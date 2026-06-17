from __future__ import annotations

import json
import os
import urllib.request

from ..config import DEFAULT_CIK_BY_SYMBOL, reliability_for_source
from ..models import CollectionRequest, FilingEvent, SourceRecord, WarningRecord, now_iso
from ..normalization import parse_datetime_to_iso
from .base import SourceOutput


class SECEdgarSource:
    name = "sec_edgar"
    source_type = "official_disclosure_api"

    def collect(self, request: CollectionRequest) -> SourceOutput:
        output = SourceOutput()
        collected_at = now_iso()
        config = request.data_source_config.get(self.name, {}) or request.data_source_config.get("sec", {})

        if "filings" not in request.normalized_requirements:
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        user_agent = config.get("user_agent") or os.getenv("SEC_USER_AGENT")
        if not user_agent:
            output.warnings.append(_warning("sec_user_agent_missing", "SEC_USER_AGENT is missing.", self.name))
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        cik = str(config.get("cik") or DEFAULT_CIK_BY_SYMBOL.get(request.normalized_symbol, ""))
        if not cik:
            output.warnings.append(_warning("sec_cik_missing", f"No CIK configured for {request.normalized_symbol}.", self.name))
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        try:
            payload = self._fetch_submissions(cik, str(user_agent))
            limit = int(config.get("limit", 40))
            output.filings.extend(self._parse_filings(payload, cik, limit, collected_at))
        except Exception as exc:  # noqa: BLE001
            output.warnings.append(_warning("sec_fetch_failed", f"SEC EDGAR fetch failed: {exc}", self.name))

        output.source_inventory.append(self._source_record(output, collected_at))
        return output

    def _fetch_submissions(self, cik: str, user_agent: str) -> dict:
        padded_cik = cik.zfill(10)
        request = urllib.request.Request(
            f"https://data.sec.gov/submissions/CIK{padded_cik}.json",
            headers={"User-Agent": user_agent},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _parse_filings(self, payload: dict, cik: str, limit: int, collected_at: str) -> list[FilingEvent]:
        recent = payload.get("filings", {}).get("recent", {})
        filings: list[FilingEvent] = []
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        period_ends = recent.get("reportDate", [])
        accessions = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        for index, form in enumerate(forms[:limit]):
            accession = _item(accessions, index)
            primary_doc = _item(docs, index)
            url = ""
            if accession and primary_doc:
                accession_path = accession.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary_doc}"
            filing_type = str(form or "")
            filings.append(
                FilingEvent(
                    filing_type=filing_type,
                    title=f"{filing_type} filing: {_item(descriptions, index) or primary_doc}",
                    filed_at=parse_datetime_to_iso(_item(dates, index)),
                    period_end=parse_datetime_to_iso(_item(period_ends, index)),
                    url=url,
                    summary_raw="Raw SEC filing metadata collected. No investment conclusion generated.",
                    source="SEC EDGAR",
                    source_reliability=reliability_for_source("SEC EDGAR"),
                    accession_number=accession,
                    collected_at=collected_at,
                    raw_metadata={
                        "form": filing_type,
                        "accession_number": accession,
                        "primary_document": primary_doc,
                    },
                )
            )
        return filings

    def _source_record(self, output: SourceOutput, collected_at: str) -> SourceRecord:
        return SourceRecord(
            name=self.name,
            source_type=self.source_type,
            enabled=True,
            used=output.records_collected > 0,
            reliability=reliability_for_source("SEC EDGAR"),
            records_collected=output.records_collected,
            failed=bool(output.warnings) and output.records_collected == 0,
            failure_reason="; ".join(w.message for w in output.warnings),
            collected_at=collected_at,
        )


def _item(values: list, index: int) -> str:
    if index >= len(values):
        return ""
    return str(values[index] or "")


def _warning(code: str, message: str, source: str) -> WarningRecord:
    return WarningRecord(code=code, message=message, source=source, severity="WARNING", collected_at=now_iso())

