"""Decision expression layer for conditional investor-specific plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from stock_agent.analysis.chinese_titles import chinese_event_title
from stock_agent.data_coverage import ProfileCoverageReport, confidence_min, evaluate_profile_coverage
from stock_agent.analysis import (
    DRIVER_COMPETITION,
    DRIVER_DELIVERY,
    DRIVER_FUNDAMENTAL,
    DRIVER_MACRO,
    DRIVER_NARRATIVE,
    DRIVER_REGULATORY,
    DRIVER_TECHNICAL,
    DRIVER_VALUATION,
    DRIVERS,
    AnalysisResult,
)


LONG_TERM_FUNDAMENTAL = "long_term_fundamental"
GROWTH_NARRATIVE = "growth_narrative"
EVENT_DRIVEN = "event_driven"
SWING_TRADER = "swing_trader"
SHORT_TERM_TRADER = "short_term_trader"
RISK_CONTROL = "risk_control"

INVESTOR_TYPE_LABELS = {
    LONG_TERM_FUNDAMENTAL: "长期基本面投资者",
    GROWTH_NARRATIVE: "成长叙事投资者",
    EVENT_DRIVEN: "事件驱动投资者",
    SWING_TRADER: "波段交易者",
    SHORT_TERM_TRADER: "短线交易者",
    RISK_CONTROL: "风险控制型投资者",
}

INVESTOR_ALIASES = {
    "long": LONG_TERM_FUNDAMENTAL,
    "long_term": LONG_TERM_FUNDAMENTAL,
    "long_term_fundamental": LONG_TERM_FUNDAMENTAL,
    "fundamental": LONG_TERM_FUNDAMENTAL,
    "growth": GROWTH_NARRATIVE,
    "growth_narrative": GROWTH_NARRATIVE,
    "event": EVENT_DRIVEN,
    "event_driven": EVENT_DRIVEN,
    "swing": SWING_TRADER,
    "swing_trader": SWING_TRADER,
    "short": SHORT_TERM_TRADER,
    "short_term": SHORT_TERM_TRADER,
    "short_term_trader": SHORT_TERM_TRADER,
    "risk": RISK_CONTROL,
    "risk_control": RISK_CONTROL,
}

PROFILE_WEIGHTS = {
    LONG_TERM_FUNDAMENTAL: {
        DRIVER_DELIVERY: 0.20,
        DRIVER_FUNDAMENTAL: 0.25,
        DRIVER_NARRATIVE: 0.12,
        DRIVER_MACRO: 0.10,
        DRIVER_COMPETITION: 0.12,
        DRIVER_REGULATORY: 0.08,
        DRIVER_TECHNICAL: 0.03,
        DRIVER_VALUATION: 0.10,
    },
    GROWTH_NARRATIVE: {
        DRIVER_DELIVERY: 0.12,
        DRIVER_FUNDAMENTAL: 0.12,
        DRIVER_NARRATIVE: 0.30,
        DRIVER_MACRO: 0.15,
        DRIVER_COMPETITION: 0.08,
        DRIVER_REGULATORY: 0.10,
        DRIVER_TECHNICAL: 0.08,
        DRIVER_VALUATION: 0.05,
    },
    EVENT_DRIVEN: {
        DRIVER_DELIVERY: 0.20,
        DRIVER_FUNDAMENTAL: 0.20,
        DRIVER_NARRATIVE: 0.15,
        DRIVER_MACRO: 0.10,
        DRIVER_COMPETITION: 0.08,
        DRIVER_REGULATORY: 0.15,
        DRIVER_TECHNICAL: 0.07,
        DRIVER_VALUATION: 0.05,
    },
    SWING_TRADER: {
        DRIVER_DELIVERY: 0.12,
        DRIVER_FUNDAMENTAL: 0.10,
        DRIVER_NARRATIVE: 0.10,
        DRIVER_MACRO: 0.18,
        DRIVER_COMPETITION: 0.05,
        DRIVER_REGULATORY: 0.10,
        DRIVER_TECHNICAL: 0.30,
        DRIVER_VALUATION: 0.05,
    },
    SHORT_TERM_TRADER: {
        DRIVER_DELIVERY: 0.08,
        DRIVER_FUNDAMENTAL: 0.06,
        DRIVER_NARRATIVE: 0.12,
        DRIVER_MACRO: 0.25,
        DRIVER_COMPETITION: 0.04,
        DRIVER_REGULATORY: 0.10,
        DRIVER_TECHNICAL: 0.30,
        DRIVER_VALUATION: 0.05,
    },
    RISK_CONTROL: {
        DRIVER_DELIVERY: 0.12,
        DRIVER_FUNDAMENTAL: 0.18,
        DRIVER_NARRATIVE: 0.06,
        DRIVER_MACRO: 0.18,
        DRIVER_COMPETITION: 0.08,
        DRIVER_REGULATORY: 0.18,
        DRIVER_TECHNICAL: 0.08,
        DRIVER_VALUATION: 0.12,
    },
}


@dataclass(frozen=True)
class InvestorProfile:
    investor_type: str
    label: str
    horizon: str
    weights: dict[str, float]
    focus_factors: tuple[str, ...]


@dataclass(frozen=True)
class DecisionPlan:
    profile: InvestorProfile
    current_bias: str
    confidence_level: str
    weighted_score: float
    profile_coverage: ProfileCoverageReport
    supporting_factors: tuple[str, ...]
    risk_factors: tuple[str, ...]
    conditional_entry_plan: tuple[str, ...]
    exit_or_reduce_conditions: tuple[str, ...]
    stop_or_invalidation_conditions: tuple[str, ...]
    no_trade_conditions: tuple[str, ...]
    contrarian_view: tuple[str, ...]
    monitoring_checklist: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)


def build_decision_plan(
    analysis: AnalysisResult,
    investor_type: str = LONG_TERM_FUNDAMENTAL,
    horizon: str = "",
) -> DecisionPlan:
    """Generate a conditional plan from second-layer analysis."""
    profile = build_investor_profile(investor_type, horizon)
    profile_coverage = evaluate_profile_coverage(analysis.data_coverage, profile.investor_type)
    weighted_score = _weighted_score(analysis, profile.weights)
    confidence_level = confidence_min(_decision_confidence(analysis), profile_coverage.confidence_cap)
    current_bias = _bias(weighted_score, confidence_level)
    support = _supporting_factors(analysis, profile)
    risks = _risk_factors(analysis, profile)
    return DecisionPlan(
        profile=profile,
        current_bias=current_bias,
        confidence_level=confidence_level,
        weighted_score=round(weighted_score, 3),
        profile_coverage=profile_coverage,
        supporting_factors=tuple(support),
        risk_factors=tuple(risks),
        conditional_entry_plan=tuple(_entry_plan(analysis, profile, weighted_score)),
        exit_or_reduce_conditions=tuple(_exit_conditions(analysis, profile)),
        stop_or_invalidation_conditions=tuple(_invalidation_conditions(analysis, profile)),
        no_trade_conditions=tuple(_no_trade_conditions(analysis, profile)),
        contrarian_view=tuple(_contrarian_view(analysis, weighted_score)),
        monitoring_checklist=tuple(_monitoring_checklist(profile)),
    )


def build_investor_profile(investor_type: str, horizon: str = "") -> InvestorProfile:
    normalized = INVESTOR_ALIASES.get(investor_type.strip().lower(), investor_type.strip().lower())
    if normalized not in PROFILE_WEIGHTS:
        normalized = LONG_TERM_FUNDAMENTAL
    weights = {driver: PROFILE_WEIGHTS[normalized].get(driver, 0.0) for driver in DRIVERS}
    focus = tuple(driver for driver, _ in sorted(weights.items(), key=lambda item: item[1], reverse=True)[:4])
    return InvestorProfile(
        investor_type=normalized,
        label=INVESTOR_TYPE_LABELS[normalized],
        horizon=horizon or _default_horizon(normalized),
        weights=weights,
        focus_factors=focus,
    )


def _weighted_score(analysis: AnalysisResult, weights: dict[str, float]) -> float:
    return sum(float(analysis.driver_scores.get(driver, 0.0)) * weight for driver, weight in weights.items())


def _bias(score: float, confidence: str) -> str:
    if confidence == "LOW":
        return "低置信度观察"
    if score > 0.18:
        return "条件偏多"
    if score < -0.18:
        return "条件偏谨慎"
    return "区间观察"


def _decision_confidence(analysis: AnalysisResult) -> str:
    if analysis.confidence_level == "LOW":
        return "LOW"
    if analysis.quality_downgrades:
        return "MEDIUM"
    return analysis.confidence_level


def _supporting_factors(analysis: AnalysisResult, profile: InvestorProfile) -> list[str]:
    factors: list[str] = []
    for driver in profile.focus_factors:
        score = analysis.driver_scores.get(driver, 0.0)
        if score > 0:
            factors.append(f"{driver} 因子为正，画像权重 {profile.weights[driver]:.0%}，当前得分 {score:.2f}。")
    for index, event in enumerate(analysis.event_signals[:3], 1):
        if event.direction == "正面":
            factors.append(f"正面事件：{_event_short_reference(event, index)}。")
    if not factors:
        factors.append("当前没有足够强的正面证据，暂以观察和条件触发为主。")
    return factors[:4]


def _risk_factors(analysis: AnalysisResult, profile: InvestorProfile) -> list[str]:
    risks: list[str] = []
    for driver in profile.focus_factors:
        score = analysis.driver_scores.get(driver, 0.0)
        if score < 0:
            risks.append(f"{driver} 因子为负，画像权重 {profile.weights[driver]:.0%}，当前得分 {score:.2f}。")
    for index, event in enumerate(analysis.event_signals[:5], 1):
        if event.direction == "负面" or _is_risk_event(event):
            label = "负面事件" if event.direction == "负面" else "风险事件"
            risks.append(f"{label}：{_event_short_reference(event, index)}。")
    risks.extend(analysis.quality_downgrades[:2])
    profile_coverage = evaluate_profile_coverage(analysis.data_coverage, profile.investor_type)
    risks.extend(profile_coverage.warnings[:2])
    if not risks:
        risks.append("主要风险来自新信息不足、估值波动和突发宏观/监管变化。")
    return risks[:5]


def _is_risk_event(event: Any) -> bool:
    text = f"{getattr(event, 'title', '')} {getattr(event, 'driver', '')} {getattr(event, 'category', '')}".lower()
    risk_terms = (
        "regulatory",
        "investigation",
        "recall",
        "lawsuit",
        "probe",
        "nhtsa",
        "ban",
        "tariff",
        "监管",
        "召回",
        "调查",
        "诉讼",
    )
    return any(term in text for term in risk_terms)


def _event_short_reference(event: Any, index: int) -> str:
    title = str(getattr(event, "title", "") or "")
    driver = getattr(event, "driver", "")
    chinese = chinese_event_title(title, driver)
    short_title = _compact_event_title(chinese)
    source = str(getattr(event, "source", "") or "未知")
    impact = float(getattr(event, "impact_score", 0.0) or 0.0)
    return f"事件#{index} {short_title}（{source}，影响分 {impact:.2f}）"


def _compact_event_title(title: str) -> str:
    text = title.split("（", 1)[0].strip()
    text = text.replace("：特斯拉", "").replace("：相关公司", "")
    text = text.replace("相关消息", "").replace("相关进展", "进展")
    return text[:28] if len(text) > 28 else text


def _entry_plan(analysis: AnalysisResult, profile: InvestorProfile, score: float) -> list[str]:
    market = analysis.market_state
    if profile.investor_type == SHORT_TERM_TRADER:
        return [
            f"回踩方案：价格接近主要支撑区 {_fmt_price(market.support_level)} 且不放量跌破时，才考虑小仓位试错。",
            f"突破方案：价格有效突破主要压力区 {_fmt_price(market.resistance_level)} 且成交量改善时，才考虑顺势参与。",
            f"ATR 参考：14 日 ATR 约 {_fmt_price(market.atr_14)}，盘中计划需按实际波动缩小仓位。",
        ]
    if profile.investor_type == LONG_TERM_FUNDAMENTAL:
        return [
            "分批方案：仅在基本面证据继续改善、估值/安全边际合理且数据质量不为 LOW 时考虑分批。",
            "安全边际：优先等待 Bear/Base 情景下沿附近或重大负面充分反映后的区间。",
            f"当前画像加权分 {score:.2f}，低于强信号阈值时不做一次性重仓判断。",
        ]
    return [
        "条件方案：只有当核心驱动因子继续改善且价格没有明显透支事件时，才考虑参与。",
        "仓位方案：数据质量为 MEDIUM 或 LOW 时降低仓位，优先等待关键事件确认。",
        f"当前画像加权分 {score:.2f}，应结合触发条件而非单一价格执行。",
    ]


def _exit_conditions(analysis: AnalysisResult, profile: InvestorProfile) -> list[str]:
    market = analysis.market_state
    conditions = [
        "核心驱动因子转负或原先支持证据被新数据推翻。",
        "价格上涨但成交量、基本面或事件确认不配合，出现明显透支。",
    ]
    if profile.investor_type in {SHORT_TERM_TRADER, SWING_TRADER}:
        conditions.append(f"价格接近或冲高回落于压力区 {_fmt_price(market.resistance_level)}，且无法继续放量。")
    else:
        conditions.append("估值进入高估区且未来盈利/叙事假设没有同步上修。")
    return conditions


def _invalidation_conditions(analysis: AnalysisResult, profile: InvestorProfile) -> list[str]:
    market = analysis.market_state
    conditions = [
        "报告中的关键正面事件被官方数据或高可信来源证伪。",
        "宏观利率、监管或竞争因素显著恶化，改变主要假设。",
    ]
    if profile.investor_type in {SHORT_TERM_TRADER, SWING_TRADER}:
        conditions.append(f"跌破主要支撑区 {_fmt_price(market.support_level)} 后无法快速收回。")
    else:
        conditions.append("交付、毛利率、现金流或管理层指引连续恶化。")
    return conditions


def _no_trade_conditions(analysis: AnalysisResult, profile: InvestorProfile) -> list[str]:
    conditions = [
        "数据质量为 LOW 或检测到样例数据参与分析。",
        "重大事件公布前后波动不可控，风险回报比无法量化。",
        "最新价格、成交量或关键宏观数据缺失。",
    ]
    if profile.investor_type in {SHORT_TERM_TRADER, SWING_TRADER}:
        conditions.extend(
            [
                "跳空过大，入场价远离支撑/压力参考区。",
                "成交量不足，突破或回踩缺少确认。",
            ]
        )
    profile_coverage = evaluate_profile_coverage(analysis.data_coverage, profile.investor_type)
    if profile_coverage.confidence_cap == "LOW":
        conditions.append("当前画像关键数据缺口过多，画像置信度上限为 LOW。")
    return conditions


def _contrarian_view(analysis: AnalysisResult, score: float) -> list[str]:
    if score >= 0:
        return [
            "反方观点：正面事件可能已经被股价提前反映，后续需要更多基本面数据验证。",
            "反方证据：若宏观利率上行、竞争加剧或监管事件升级，当前偏多条件会失效。",
            "关键验证：交付量、库存、毛利率、成交量和高可信新闻源的后续确认。",
        ]
    return [
        "反方观点：负面预期可能已经被市场计入，若关键数据好于预期，价格可能修复。",
        "反方证据：若技术面重新转强、宏观风险缓和或正面催化剂兑现，谨慎判断会失效。",
        "关键验证：支撑区表现、成交量变化、事件后价格反应和官方披露。",
    ]


def _monitoring_checklist(profile: InvestorProfile) -> list[str]:
    checklist = [
        "最新价格、成交量、主要支撑/压力和波动率。",
        "交付量、库存、价格调整、毛利率、EPS 和自由现金流。",
        "10 年期/2 年期美债收益率、美元指数、纳指、VIX 和 CPI。",
        "监管、诉讼、召回、关税、补贴和竞争对手动态。",
    ]
    if profile.investor_type == GROWTH_NARRATIVE:
        checklist.append("FSD、Robotaxi、AI 里程碑和市场叙事强弱。")
    if profile.investor_type in {SHORT_TERM_TRADER, SWING_TRADER}:
        checklist.append("ATR、突破/回踩确认、期权隐含波动率和资金流。")
    return checklist


def _default_horizon(investor_type: str) -> str:
    return {
        LONG_TERM_FUNDAMENTAL: "6-36 个月",
        GROWTH_NARRATIVE: "6-36 个月",
        EVENT_DRIVEN: "1 周-3 个月",
        SWING_TRADER: "1 周-3 个月",
        SHORT_TERM_TRADER: "1-5 天",
        RISK_CONTROL: "按风险暴露动态调整",
    }[investor_type]


def _fmt_price(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "无"


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value
