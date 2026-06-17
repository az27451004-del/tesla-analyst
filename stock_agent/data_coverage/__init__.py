"""Data source roadmap and profile-specific coverage gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Iterable


DOMAIN_MARKET_DATA = "market_data_quality"
DOMAIN_FUNDAMENTALS = "fundamentals_expectations"
DOMAIN_MACRO = "macro_variables"
DOMAIN_INDUSTRY = "industry_data"
DOMAIN_OPTIONS_FLOW = "options_and_flow"
DOMAIN_BACKTEST = "backtesting"

PRIORITY_P1 = "P1"
PRIORITY_P2 = "P2"
PRIORITY_P3 = "P3"

CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass(frozen=True)
class DataSourceRoadmapItem:
    domain: str
    label: str
    priority: str
    low_cost_sources: tuple[str, ...]
    paid_enhancement_sources: tuple[str, ...]
    data_requirements: tuple[str, ...]
    affected_drivers: tuple[str, ...]
    affected_profiles: tuple[str, ...]
    current_status: str


@dataclass(frozen=True)
class DataGap:
    domain: str
    label: str
    severity: str
    message: str
    affected_drivers: tuple[str, ...]
    affected_profiles: tuple[str, ...]
    recommended_sources: tuple[str, ...]
    confidence_cap: str


@dataclass(frozen=True)
class DataCoverageReport:
    coverage_level: str
    confidence_cap: str
    satisfied_domains: tuple[str, ...]
    missing_domains: tuple[str, ...]
    gaps: tuple[DataGap, ...]
    roadmap: tuple[DataSourceRoadmapItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)


@dataclass(frozen=True)
class ProfileCoverageReport:
    investor_type: str
    coverage_level: str
    confidence_cap: str
    critical_gaps: tuple[DataGap, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)


def build_data_source_roadmap() -> tuple[DataSourceRoadmapItem, ...]:
    """Return the production data roadmap without requiring external integrations."""
    return (
        DataSourceRoadmapItem(
            domain=DOMAIN_MARKET_DATA,
            label="高质量行情",
            priority=PRIORITY_P1,
            low_cost_sources=("Alpha Vantage", "Stooq/Yahoo Finance 本地导入", "Nasdaq Data Link 免费/低价数据集"),
            paid_enhancement_sources=("Polygon", "IEX exchange feeds", "Bloomberg/FactSet 后期增强"),
            data_requirements=("market_data",),
            affected_drivers=("技术面/期权/资金流", "估值/安全边际"),
            affected_profiles=("swing_trader", "short_term_trader", "risk_control"),
            current_status="已有 Alpha Vantage/本地 CSV；需提高稳定性、成交量和复权数据覆盖。",
        ),
        DataSourceRoadmapItem(
            domain=DOMAIN_FUNDAMENTALS,
            label="财报与预期",
            priority=PRIORITY_P1,
            low_cost_sources=("SEC EDGAR", "公司 IR", "earnings call transcript 本地导入", "分析师预期 CSV"),
            paid_enhancement_sources=("Nasdaq Data Link premium", "FactSet", "Bloomberg"),
            data_requirements=("filings", "financial_metrics", "research_reports"),
            affected_drivers=("毛利率/EPS/现金流", "估值/安全边际"),
            affected_profiles=("long_term_fundamental", "growth_narrative", "event_driven", "risk_control"),
            current_status="已有 SEC metadata 和本地 research_report 模型；缺结构化财务指标、预期和 transcript。",
        ),
        DataSourceRoadmapItem(
            domain=DOMAIN_MACRO,
            label="宏观变量",
            priority=PRIORITY_P1,
            low_cost_sources=("FRED", "公开 VIX/指数 CSV", "美元指数/纳指本地导入"),
            paid_enhancement_sources=("Nasdaq Data Link premium", "Polygon indices", "Bloomberg/FactSet 后期增强"),
            data_requirements=("macro_data",),
            affected_drivers=("利率/美元/纳指", "估值/安全边际"),
            affected_profiles=("growth_narrative", "swing_trader", "short_term_trader", "risk_control"),
            current_status="已有 FRED source；默认序列仍需扩展美元指数、纳指、VIX、信用利差等。",
        ),
        DataSourceRoadmapItem(
            domain=DOMAIN_INDUSTRY,
            label="行业数据",
            priority=PRIORITY_P2,
            low_cost_sources=("本地 CSV/JSON", "公司交付公告", "行业协会公开数据", "监管/召回公开数据"),
            paid_enhancement_sources=("行业数据库", "Bloomberg/FactSet 后期增强"),
            data_requirements=("industry_data", "official_events"),
            affected_drivers=("交付/库存/价格", "竞争格局", "监管/诉讼/政策"),
            affected_profiles=("long_term_fundamental", "growth_narrative", "event_driven", "risk_control"),
            current_status="已有本地 industry_data 模型；缺自动化行业销量、库存、补贴、关税和竞争数据。",
        ),
        DataSourceRoadmapItem(
            domain=DOMAIN_OPTIONS_FLOW,
            label="期权与资金流",
            priority=PRIORITY_P2,
            low_cost_sources=("IBKR 只读接口", "本地期权链/put-call CSV", "公开持仓 CSV"),
            paid_enhancement_sources=("Polygon options", "ORATS/SpotGamma 类数据", "Bloomberg/FactSet 后期增强"),
            data_requirements=("options_data", "broker_account_data"),
            affected_drivers=("技术面/期权/资金流",),
            affected_profiles=("event_driven", "swing_trader", "short_term_trader", "risk_control"),
            current_status="已有 IBKR 只读 option_data 模型；缺 IV、put/call、gamma exposure、机构资金流。",
        ),
        DataSourceRoadmapItem(
            domain=DOMAIN_BACKTEST,
            label="严格回测",
            priority=PRIORITY_P1,
            low_cost_sources=("本地历史行情", "本地事件快照", "walk-forward validation 脚本"),
            paid_enhancement_sources=("高质量历史数据库", "专业交易成本/盘口数据"),
            data_requirements=("market_data", "news_events"),
            affected_drivers=("技术面/期权/资金流", "估值/安全边际"),
            affected_profiles=(
                "long_term_fundamental",
                "growth_narrative",
                "event_driven",
                "swing_trader",
                "short_term_trader",
                "risk_control",
            ),
            current_status="尚未实现回测模块；需加入 walk-forward、特征泄漏检查、交易成本和滑点。",
        ),
    )


def evaluate_data_coverage(
    *,
    has_market_data: bool,
    has_volume: bool,
    has_filings: bool,
    has_financial_metrics: bool,
    has_research_reports: bool,
    has_macro_data: bool,
    has_industry_data: bool,
    has_official_events: bool,
    has_options_data: bool,
    has_broker_account_data: bool,
    has_backtest: bool = False,
    sample_data_detected: bool = False,
    stale_market_data: bool = False,
) -> DataCoverageReport:
    roadmap = build_data_source_roadmap()
    gaps: list[DataGap] = []
    satisfied: list[str] = []

    _add_gap_or_satisfied(
        gaps,
        satisfied,
        domain=DOMAIN_MARKET_DATA,
        condition=has_market_data and has_volume and not stale_market_data,
        severity="CRITICAL" if not has_market_data else "WARNING",
        message=_market_message(has_market_data, has_volume, stale_market_data),
        confidence_cap="LOW" if not has_market_data else "MEDIUM",
    )
    _add_gap_or_satisfied(
        gaps,
        satisfied,
        domain=DOMAIN_FUNDAMENTALS,
        condition=has_filings and has_financial_metrics,
        severity="WARNING",
        message="缺少结构化财报指标、分析师预期或 earnings call transcript，基本面和估值置信度降级。",
        confidence_cap="MEDIUM",
    )
    _add_gap_or_satisfied(
        gaps,
        satisfied,
        domain=DOMAIN_MACRO,
        condition=has_macro_data,
        severity="WARNING",
        message="缺少宏观变量，利率、美元、纳指、VIX、CPI 对估值和风险偏好的影响无法充分评估。",
        confidence_cap="MEDIUM",
    )
    _add_gap_or_satisfied(
        gaps,
        satisfied,
        domain=DOMAIN_INDUSTRY,
        condition=has_industry_data and has_official_events,
        severity="INFO",
        message="缺少行业销量、库存、补贴、关税、竞争和监管细分数据，行业/竞争判断降级。",
        confidence_cap="MEDIUM",
    )
    _add_gap_or_satisfied(
        gaps,
        satisfied,
        domain=DOMAIN_OPTIONS_FLOW,
        condition=has_options_data or has_broker_account_data,
        severity="INFO",
        message="缺少期权与资金流数据，短线、波段、事件交易计划置信度降级。",
        confidence_cap="MEDIUM",
    )
    _add_gap_or_satisfied(
        gaps,
        satisfied,
        domain=DOMAIN_BACKTEST,
        condition=has_backtest,
        severity="WARNING",
        message="缺少严格回测，第三层条件化计划尚未经过 walk-forward、特征泄漏、交易成本和滑点验证。",
        confidence_cap="MEDIUM",
    )
    if sample_data_detected:
        item = _roadmap_item(DOMAIN_MARKET_DATA)
        gaps.append(
            DataGap(
                domain=DOMAIN_MARKET_DATA,
                label="样例数据",
                severity="CRITICAL",
                message="检测到样例或 fictional 数据，不能作为真实投资判断。",
                affected_drivers=item.affected_drivers,
                affected_profiles=item.affected_profiles,
                recommended_sources=item.low_cost_sources,
                confidence_cap="LOW",
            )
        )

    confidence_cap = _minimum_confidence([gap.confidence_cap for gap in gaps], default="HIGH")
    missing = tuple(_dedupe(gap.domain for gap in gaps))
    if confidence_cap == "LOW":
        coverage_level = "LOW"
    elif gaps:
        coverage_level = "MEDIUM"
    else:
        coverage_level = "HIGH"
    return DataCoverageReport(
        coverage_level=coverage_level,
        confidence_cap=confidence_cap,
        satisfied_domains=tuple(_dedupe(satisfied)),
        missing_domains=missing,
        gaps=tuple(gaps),
        roadmap=roadmap,
    )


def evaluate_profile_coverage(data_coverage: DataCoverageReport, investor_type: str) -> ProfileCoverageReport:
    normalized = investor_type.strip().lower()
    critical_domains = _profile_critical_domains(normalized)
    relevant_gaps = [
        gap
        for gap in data_coverage.gaps
        if normalized in gap.affected_profiles or gap.domain in critical_domains or gap.confidence_cap == "LOW"
    ]
    confidence_cap = _minimum_confidence([gap.confidence_cap for gap in relevant_gaps], default=data_coverage.confidence_cap)
    if any(gap.domain in critical_domains and gap.severity in {"CRITICAL", "WARNING"} for gap in relevant_gaps):
        confidence_cap = _minimum_confidence([confidence_cap, "MEDIUM"], default=confidence_cap)
    if any(gap.confidence_cap == "LOW" for gap in relevant_gaps):
        confidence_cap = "LOW"
    warnings = tuple(gap.message for gap in relevant_gaps)
    return ProfileCoverageReport(
        investor_type=normalized,
        coverage_level="LOW" if confidence_cap == "LOW" else "MEDIUM" if relevant_gaps else "HIGH",
        confidence_cap=confidence_cap,
        critical_gaps=tuple(relevant_gaps),
        warnings=warnings,
    )


def confidence_min(*levels: str) -> str:
    return _minimum_confidence(levels, default="HIGH")


def _add_gap_or_satisfied(
    gaps: list[DataGap],
    satisfied: list[str],
    *,
    domain: str,
    condition: bool,
    severity: str,
    message: str,
    confidence_cap: str,
) -> None:
    item = _roadmap_item(domain)
    if condition:
        satisfied.append(domain)
        return
    gaps.append(
        DataGap(
            domain=domain,
            label=item.label,
            severity=severity,
            message=message,
            affected_drivers=item.affected_drivers,
            affected_profiles=item.affected_profiles,
            recommended_sources=item.low_cost_sources,
            confidence_cap=confidence_cap,
        )
    )


def _market_message(has_market_data: bool, has_volume: bool, stale_market_data: bool) -> str:
    if not has_market_data:
        return "缺少高质量行情数据，市场状态、技术面、回测和交易计划无法形成高置信度。"
    if stale_market_data:
        return "价格数据过期，市场状态和交易计划置信度降级。"
    if not has_volume:
        return "缺少成交量数据，突破/回踩、资金流和技术面确认能力下降。"
    return "行情数据覆盖不足。"


def _roadmap_item(domain: str) -> DataSourceRoadmapItem:
    for item in build_data_source_roadmap():
        if item.domain == domain:
            return item
    raise KeyError(domain)


def _profile_critical_domains(investor_type: str) -> set[str]:
    return {
        "long_term_fundamental": {DOMAIN_FUNDAMENTALS, DOMAIN_MACRO, DOMAIN_BACKTEST},
        "growth_narrative": {DOMAIN_MACRO, DOMAIN_INDUSTRY, DOMAIN_FUNDAMENTALS},
        "event_driven": {DOMAIN_FUNDAMENTALS, DOMAIN_OPTIONS_FLOW, DOMAIN_BACKTEST},
        "swing_trader": {DOMAIN_MARKET_DATA, DOMAIN_MACRO, DOMAIN_OPTIONS_FLOW, DOMAIN_BACKTEST},
        "short_term_trader": {DOMAIN_MARKET_DATA, DOMAIN_MACRO, DOMAIN_OPTIONS_FLOW, DOMAIN_BACKTEST},
        "risk_control": {DOMAIN_FUNDAMENTALS, DOMAIN_MACRO, DOMAIN_INDUSTRY, DOMAIN_OPTIONS_FLOW, DOMAIN_BACKTEST},
    }.get(investor_type, {DOMAIN_FUNDAMENTALS, DOMAIN_MACRO, DOMAIN_BACKTEST})


def _minimum_confidence(levels: Iterable[str], default: str) -> str:
    normalized = [level for level in levels if level in CONFIDENCE_ORDER]
    if not normalized:
        return default
    return min(normalized, key=lambda item: CONFIDENCE_ORDER[item])


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value

