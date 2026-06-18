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
            output.filings.extend(self._parse_filings(payload, cik, limit, collected_at, request.company_name or request.normalized_symbol))
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

    def _parse_filings(self, payload: dict, cik: str, limit: int, collected_at: str, company_name: str) -> list[FilingEvent]:
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
            original_title = f"{filing_type} filing: {_item(descriptions, index) or primary_doc}"
            chinese_label, chinese_description, importance, display_group = _filing_display_metadata(filing_type)
            company = company_name or "公司"
            filings.append(
                FilingEvent(
                    filing_type=filing_type,
                    title=f"{chinese_label}：{company} 最新披露",
                    filed_at=parse_datetime_to_iso(_item(dates, index)),
                    period_end=parse_datetime_to_iso(_item(period_ends, index)),
                    url=url,
                    summary_raw=f"{chinese_description}。仅采集 SEC 披露元数据，不生成投资结论。",
                    source="SEC EDGAR",
                    source_reliability=reliability_for_source("SEC EDGAR"),
                    accession_number=accession,
                    collected_at=collected_at,
                    raw_metadata={
                        "form": filing_type,
                        "original_title": original_title,
                        "chinese_title": f"{chinese_label}：{company} 最新披露",
                        "chinese_form_label": chinese_label,
                        "chinese_form_description": chinese_description,
                        "sec_importance": importance,
                        "display_group": display_group,
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


def _filing_display_metadata(form: str) -> tuple[str, str, str, str]:
    normalized = form.strip().upper()
    mapping = {
        "10-K": ("年度报告（10-K）", "公司年度财务与经营情况披露", "core", "财报披露"),
        "10-K/A": ("年度报告修订（10-K/A）", "年度报告的修订披露", "core", "财报披露"),
        "10-Q": ("季度财报（10-Q）", "公司季度财务与经营情况披露", "core", "财报披露"),
        "10-Q/A": ("季度财报修订（10-Q/A）", "季度报告的修订披露", "core", "财报披露"),
        "8-K": ("重大事项报告（8-K）", "公司重大事项或临时事件披露", "material", "重大披露"),
        "8-K/A": ("重大事项报告修订（8-K/A）", "重大事项报告的修订披露", "material", "重大披露"),
        "SD": ("专项披露（SD）", "冲突矿产或供应链相关专项披露", "material", "重大披露"),
        "4": ("内部人持股变动（Form 4）", "董事、高管或大股东持股变动披露", "low", "持股/登记类披露"),
        "144": ("拟出售证券通知（Form 144）", "关联方或受限证券拟出售通知", "low", "持股/登记类披露"),
        "SCHEDULE 13G": ("机构持股披露（13G）", "机构或大股东被动持股披露", "low", "持股/登记类披露"),
        "SCHEDULE 13G/A": ("机构持股修订（13G/A）", "机构或大股东被动持股修订披露", "low", "持股/登记类披露"),
        "SCHEDULE 13D": ("主动持股披露（13D）", "投资者主动持股和意图披露", "medium", "持股/登记类披露"),
        "SCHEDULE 13D/A": ("主动持股修订（13D/A）", "主动持股披露的修订", "medium", "持股/登记类披露"),
        "S-8": ("员工股权激励登记（S-8）", "员工股权激励相关证券登记", "low", "持股/登记类披露"),
        "DEFA14A": ("股东会议补充材料（DEFA14A）", "股东会议或代理投票补充材料", "low", "持股/登记类披露"),
    }
    if normalized in mapping:
        return mapping[normalized]
    return (f"SEC 披露（{normalized or '未知表单'}）", "SEC 披露文件", "low", "其他披露")


def _warning(code: str, message: str, source: str) -> WarningRecord:
    return WarningRecord(code=code, message=message, source=source, severity="WARNING", collected_at=now_iso())
