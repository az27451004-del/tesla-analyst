from __future__ import annotations

import json
import os
import urllib.request

from tsla_agent.config import CIK_BY_SYMBOL, AgentConfig
from tsla_agent.connectors.base import CollectionResult
from tsla_agent.models import Event


class SECConnector:
    name = "sec"

    def collect(self, config: AgentConfig) -> CollectionResult:
        user_agent = os.getenv("SEC_USER_AGENT")
        if not user_agent:
            return CollectionResult(warnings=["SEC_USER_AGENT 未设置，跳过 SEC 披露。"])

        cik = CIK_BY_SYMBOL.get(config.normalized_symbol)
        if not cik:
            return CollectionResult(warnings=[f"未配置 {config.normalized_symbol} 的 CIK，跳过 SEC。"])

        try:
            payload = self._fetch_submissions(cik, user_agent)
            events = self._parse_filings(payload, cik, config.max_events)
            return CollectionResult(events=events)
        except Exception as exc:  # noqa: BLE001
            return CollectionResult(warnings=[f"SEC 披露获取失败：{exc}"])

    def _fetch_submissions(self, cik: str, user_agent: str) -> dict:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _parse_filings(self, payload: dict, cik: str, limit: int) -> list[Event]:
        recent = payload.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        events: list[Event] = []
        for index, form in enumerate(forms[:limit]):
            accession = _item(accessions, index)
            primary_doc = _item(docs, index)
            url = ""
            if accession and primary_doc:
                accession_path = accession.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary_doc}"
            form_text = str(form)
            events.append(
                Event(
                    source="SEC",
                    title=f"{form_text} filing: {_item(descriptions, index) or primary_doc}",
                    summary=f"Tesla submitted SEC form {form_text}. Review the filing for accounting, risk, capital structure, insider trading, or operational updates.",
                    url=url,
                    published_at=_item(dates, index),
                    category=_category_for_form(form_text),
                    tags=(form_text,),
                    raw={
                        "form": form_text,
                        "accession": accession,
                        "primary_document": primary_doc,
                    },
                )
            )
        return events


def _item(values: list, index: int) -> str:
    if index >= len(values):
        return ""
    return str(values[index] or "")


def _category_for_form(form: str) -> str:
    if form in {"10-K", "10-Q"}:
        return "earnings"
    if form in {"8-K", "6-K"}:
        return "company_update"
    if form in {"4", "3", "5"}:
        return "insider"
    return "filing"
