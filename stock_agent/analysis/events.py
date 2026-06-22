"""Event-to-signal mapping for the second analysis layer."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .constants import (
    DRIVER_COMPETITION,
    DRIVER_DELIVERY,
    DRIVER_ENERGY,
    DRIVER_FUNDAMENTAL,
    DRIVER_MACRO,
    DRIVER_NARRATIVE,
    DRIVER_REGULATORY,
    DRIVER_TECHNICAL,
    DRIVER_VALUATION,
    DRIVERS,
    NEGATIVE_TERMS,
    POSITIVE_TERMS,
)
from .models import EventSignal, MarketState
from .utils import field_value, number


def build_event_signals(events: Iterable[Any]) -> tuple[EventSignal, ...]:
    signals = (_event_signal(event) for event in events)
    return tuple(sorted(signals, key=lambda item: item.impact_score, reverse=True))


def build_driver_scores(
    events: tuple[EventSignal, ...],
    market: MarketState,
    *,
    macro_data: Iterable[Any] = (),
    industry_data: Iterable[Any] = (),
) -> dict[str, float]:
    scores = {driver: 0.0 for driver in DRIVERS}
    for driver in DRIVERS:
        driver_events = [event for event in events if event.driver == driver][:5]
        if not driver_events:
            continue
        weighted_sum = 0.0
        weight_total = 0.0
        for index, event in enumerate(driver_events):
            signed = event.impact_score if event.direction != "负面" else -event.impact_score
            reliability_weight = 0.35 + min(1.0, max(0.0, event.source_reliability)) * 0.65
            rank_decay = 1.0 / (1.0 + index * 0.45)
            weight = reliability_weight * rank_decay
            weighted_sum += signed * weight
            weight_total += weight
        conviction = min(1.0, weight_total / 2.5)
        scores[driver] = (weighted_sum / max(weight_total, 0.001)) * conviction
    if market.last_close is not None:
        technical = 0.15
        if market.trend_label in {"多头趋势", "短中期偏强"}:
            technical = 0.35
        elif market.trend_label in {"空头趋势", "短中期偏弱"}:
            technical = -0.35
        scores[DRIVER_TECHNICAL] += technical
    macro_score = _structured_macro_score(macro_data)
    if macro_score is not None:
        scores[DRIVER_MACRO] = _combine_scores(scores[DRIVER_MACRO], macro_score)
    delivery_score = _structured_delivery_score(industry_data)
    if delivery_score is not None:
        scores[DRIVER_DELIVERY] = _combine_scores(scores[DRIVER_DELIVERY], delivery_score)
    return {driver: round(max(-1.0, min(1.0, value)), 3) for driver, value in scores.items()}


def _event_signal(event: Any) -> EventSignal:
    title = str(field_value(event, "title", "title_or_metric", "metric_name", default="") or "")
    summary = str(field_value(event, "summary", "summary_raw", default="") or "")
    category = str(field_value(event, "category", "event_type", "filing_type", default="news") or "news")
    text = f"{title} {summary} {category}".lower()
    sentiment = number(field_value(event, "sentiment"), _keyword_sentiment(text))
    impact = number(field_value(event, "impact_score"), 0.0)
    reliability = number(field_value(event, "source_reliability"), 0.5)
    raw_metadata = field_value(event, "raw_metadata", default={}) or {}
    driver = _driver_for_text(text, category)
    direction = "正面" if sentiment > 0.15 else "负面" if sentiment < -0.15 else "中性"
    base = _driver_base_weight(driver)
    relevance = _event_relevance(raw_metadata)
    relevance_weight = 0.45 + relevance * 0.55
    model_score = base + abs(sentiment) * 0.18 + reliability * 0.12
    impact_score = max(impact, model_score)
    impact_score *= relevance_weight
    impact_cap = _impact_cap(category, text, relevance, raw_metadata)
    impact_score = min(impact_cap, impact_score)
    score_breakdown = _score_breakdown(
        base=base,
        sentiment=sentiment,
        reliability=reliability,
        relevance=relevance,
        relevance_weight=relevance_weight,
        supplied_impact=impact,
        model_score=model_score,
        impact_cap=impact_cap,
        final_score=impact_score,
    )
    quantitative_evidence = _quantitative_evidence(event, raw_metadata)
    return EventSignal(
        title=title,
        source=str(field_value(event, "source", "publisher", "institution", default="") or ""),
        published_at=_event_timestamp(event, raw_metadata),
        category=category or "news",
        driver=driver,
        direction=direction,
        impact_score=round(impact_score, 3),
        time_window=_time_window(text),
        surprise_level="待验证" if "guidance" in text or "consensus" in text or "预期" in text else "未知",
        source_reliability=round(reliability, 3),
        evidence=summary[:240],
        impact_reason=_impact_reason(driver, direction, title, summary, sentiment),
        counterpoint=_counterpoint(driver, direction),
        quantitative_evidence=quantitative_evidence,
        score_breakdown=score_breakdown,
    )


def _event_timestamp(event: Any, raw_metadata: Any) -> str:
    direct = field_value(event, "published_at", "filed_at", "date", "date_time", "collected_at", default="")
    if direct not in (None, ""):
        return str(direct)
    if isinstance(raw_metadata, dict):
        for key in ("published_at", "filed_at", "date", "date_time", "collected_at"):
            value = raw_metadata.get(key)
            if value not in (None, ""):
                return str(value)
    return ""


def _score_breakdown(
    *,
    base: float,
    sentiment: float,
    reliability: float,
    relevance: float,
    relevance_weight: float,
    supplied_impact: float,
    model_score: float,
    impact_cap: float,
    final_score: float,
) -> tuple[str, ...]:
    parts = [
        f"驱动因子基础权重 {base:.2f}",
        f"关键词情绪 {sentiment:+.2f}，情绪贡献 {abs(sentiment) * 0.18:.2f}",
        f"来源可信度 {reliability:.2f}，可信度贡献 {reliability * 0.12:.2f}",
        f"TSLA 相关度 {relevance:.2f}，相关度权重 {relevance_weight:.2f}",
    ]
    if supplied_impact > 0:
        parts.append(f"来源预置影响分 {supplied_impact:.2f}，与模型分 {model_score:.2f} 取较高值")
    else:
        parts.append(f"模型原始分 {model_score:.2f}")
    if impact_cap < 0.999:
        parts.append(f"事件类型上限 {impact_cap:.2f}")
    parts.append(f"最终影响分 {final_score:.3f}")
    return tuple(parts)


def _quantitative_evidence(event: Any, raw_metadata: Any) -> tuple[str, ...]:
    evidence: list[str] = []
    value = number(field_value(event, "value"), None)
    unit = str(field_value(event, "unit", default="") or "")
    if value is not None:
        evidence.append(f"结构化数值 {value:g}{unit}")
    if isinstance(raw_metadata, dict):
        labels = {
            "change_pct": "环比/阶段变化",
            "pct_change": "变化幅度",
            "yoy_change_pct": "同比变化",
            "qoq_change_pct": "环比变化",
            "target_price": "目标价",
            "price_target": "目标价",
            "estimate": "预估值",
            "consensus": "一致预期",
            "actual": "实际值",
            "deliveries": "交付量",
            "inventory": "库存",
        }
        for key, label in labels.items():
            if key in raw_metadata and raw_metadata.get(key) not in (None, ""):
                evidence.append(f"{label}：{raw_metadata.get(key)}")
    if evidence:
        return tuple(evidence[:5])
    return ("原始事件未提供可量化数值；当前方向主要来自标题/摘要关键词和来源可信度。",)


def _impact_reason(driver: str, direction: str, title: str, summary: str, sentiment: float) -> str:
    text = f"{title} {summary}".lower()
    if driver == DRIVER_NARRATIVE:
        reason = "FSD/Robotaxi/AI 事件会影响市场对特斯拉软件收入、自动驾驶商业化和长期估值倍数的预期。"
    elif driver == DRIVER_DELIVERY:
        reason = "交付、库存和价格会直接影响收入确认、产能利用率、毛利率和需求强弱判断。"
    elif driver == DRIVER_MACRO:
        reason = "利率、美元和纳指会影响成长股折现率、风险偏好和特斯拉估值倍数。"
    elif driver == DRIVER_FUNDAMENTAL:
        reason = "财报、EPS、现金流和毛利率会直接影响盈利质量和估值承接能力。"
    elif driver == DRIVER_REGULATORY:
        reason = "监管、召回和政策事件会改变合规成本、补贴环境和业务推进节奏。"
    elif driver == DRIVER_COMPETITION:
        reason = "竞争格局变化会影响市场份额、定价能力和长期利润率。"
    elif driver == DRIVER_ENERGY:
        reason = "能源、储能、供应链和原材料事件会影响成本、产能和第二增长曲线。"
    elif driver == DRIVER_VALUATION:
        reason = "评级、目标价和估值讨论会影响短期资金预期，但需要回到基本面验证。"
    else:
        reason = "技术面、期权和资金流事件会影响短期供需、动量和波动率。"

    if direction == "正面":
        prefix = "判为正面："
    elif direction == "负面":
        prefix = "判为负面："
    else:
        prefix = "判为中性："
    keyword_note = _matched_keyword_note(text, sentiment)
    return f"{prefix}{reason}{keyword_note}"


def _matched_keyword_note(text: str, sentiment: float) -> str:
    positives = [term for term in sorted(POSITIVE_TERMS, key=lambda item: (-len(item), item)) if term in text][:3]
    negatives = [term for term in sorted(NEGATIVE_TERMS, key=lambda item: (-len(item), item)) if term in text][:3]
    matched = positives + negatives
    if not matched:
        return " 未识别到强正负关键词，方向置信度需要人工复核。"
    return f" 识别关键词：{', '.join(matched)}；关键词情绪 {sentiment:+.2f}。"


def _counterpoint(driver: str, direction: str) -> str:
    if driver == DRIVER_NARRATIVE:
        base = "反方：自动驾驶审批或叙事进展可能尚未转化为可审计收入，监管限制、事故责任和商业化时间表仍可能压低估值。"
    elif driver == DRIVER_DELIVERY:
        base = "反方：交付增加若依赖降价或渠道库存，可能牺牲毛利率；交付预测也可能被季末物流和地区结构扰动。"
    elif driver == DRIVER_MACRO:
        base = "反方：单个宏观指标不能代表完整金融条件，纳指强势也可能掩盖利率或美元压力。"
    elif driver == DRIVER_FUNDAMENTAL:
        base = "反方：单季财务改善可能来自一次性项目或成本递延，需要结合毛利率、现金流和指引验证。"
    elif driver == DRIVER_REGULATORY:
        base = "反方：监管风险的实际财务影响取决于处罚规模、整改周期和是否影响销量。"
    elif driver == DRIVER_COMPETITION:
        base = "反方：竞争新闻未必能量化到特斯拉份额，价格带、地区和车型结构需要进一步拆分。"
    elif driver == DRIVER_ENERGY:
        base = "反方：储能或供应链利好可能受执行进度、原材料价格和项目确认节奏影响。"
    elif driver == DRIVER_VALUATION:
        base = "反方：评级或目标价变化是二级市场观点，不等同于公司经营事实。"
    else:
        base = "反方：技术面和资金流信号有效期短，可能被宏观消息、财报或流动性快速反转。"
    if direction == "负面":
        return base.replace("反方：", "反方利好可能：", 1)
    return base


def _driver_for_text(text: str, category: str) -> str:
    category = category.lower()
    if category in {"10-k", "10-k/a", "10-q", "10-q/a", "20-f", "annual report", "quarterly report", "financial_metric", "earnings"}:
        return DRIVER_FUNDAMENTAL
    if category in {"8-k", "regulatory"}:
        return DRIVER_REGULATORY
    if category in {"4", "form 4", "144", "s-8", "defa14a", "schedule 13g", "schedule 13g/a", "schedule 13d", "schedule 13d/a", "filing"}:
        return DRIVER_REGULATORY
    if category in {"delivery", "company_update"}:
        return DRIVER_DELIVERY
    if any(term in text for term in ("cathie wood", "ark invest", "arkk", "etf", "large holder", "fund manager", "institutional", "stock holdings", "shares acquired", "shares sold", "options", "option", "put/call", "volume", "technical", "resistance", "momentum")):
        return DRIVER_TECHNICAL
    if any(
        term in text
        for term in (
            "tax credit",
            "incentive",
            "support withdrawn",
            "support measures withdrawn",
            "subsidy",
            "software ban",
            "tariff",
            "policy",
            "nhtsa",
            "senator",
            "safety data",
            "misleading",
            "sanction",
            "sanctions",
            "export control",
            "white house",
            "executive order",
        )
    ):
        return DRIVER_REGULATORY
    if _has_any_phrase(text, ("fsd", "robotaxi", "autonomy", "autonomous", "ai", "ai chip", "artificial intelligence", "spacex", "musk")):
        return DRIVER_NARRATIVE
    if any(term in text for term in ("delivery", "deliveries", "inventory", "price cut", "vehicle sales")):
        return DRIVER_DELIVERY
    if any(term in text for term in ("analyst", "rating", "price target", "target price", "upgrade", "downgrade", "valuation", "multiple", "fair value", "margin of safety", "jpmorgan", "goldman", "morgan stanley", "wedbush")):
        return DRIVER_VALUATION
    if any(term in text for term in ("earnings", "eps", "margin", "revenue", "cash flow", "guidance")):
        return DRIVER_FUNDAMENTAL
    if category == "macro" or any(
        term in text
        for term in (
            "rate",
            "fed",
            "cpi",
            "inflation",
            "treasury",
            "dollar",
            "nasdaq",
            "vix",
            "jerome powell",
            "federal reserve",
            "white house",
            "president speech",
            "election policy",
            "geopolitical",
        )
    ):
        return DRIVER_MACRO
    if any(term in text for term in ("byd", "rivian", "lucid", "ford", "gm", "competition", "market share", "price war")):
        return DRIVER_COMPETITION
    if any(term in text for term in ("sec", "recall", "lawsuit", "investigation", "regulatory", "tariff", "subsidy")):
        return DRIVER_REGULATORY
    if any(
        term in text
        for term in (
            "energy",
            "storage",
            "battery",
            "supply",
            "lithium",
            "raw material",
            "ev demand",
            "ev growth",
            "oil",
            "crude",
            "hormuz",
            "strait of hormuz",
            "shipping lane",
        )
    ):
        return DRIVER_ENERGY
    return DRIVER_TECHNICAL


def _structured_macro_score(points: Iterable[Any]) -> float | None:
    scores: list[float] = []
    for point in points:
        name = str(field_value(point, "indicator_name", "series_id", default="") or "").lower()
        metadata = field_value(point, "raw_metadata", default={}) or {}
        if isinstance(metadata, dict):
            name = f"{name} {metadata.get('series_id', '')}".lower()
        value = number(field_value(point, "value"), None)
        if value is None:
            continue
        if any(term in name for term in ("10y", "2y", "treasury", "yield", "dgs10", "dgs2", "fedfunds", "federal funds")):
            scores.append(_rate_level_score(value))
        elif any(term in name for term in ("nasdaq", "vix", "dollar", "usd", "cpi", "unemployment", "unrate")):
            change = _metadata_change(metadata)
            if change is not None:
                scores.append(max(-0.35, min(0.35, change / 10.0)))
    if not scores:
        return None
    return sum(scores) / len(scores)


def _rate_level_score(value: float) -> float:
    if value >= 5.0:
        return -0.28
    if value >= 4.5:
        return -0.20
    if value >= 4.0:
        return -0.12
    if value >= 3.5:
        return -0.05
    if value >= 2.5:
        return 0.08
    return 0.16


def _structured_delivery_score(points: Iterable[Any]) -> float | None:
    scores: list[float] = []
    for point in points:
        title = str(field_value(point, "title_or_metric", "title", default="") or "")
        metadata = field_value(point, "raw_metadata", default={}) or {}
        text = f"{title} {metadata if isinstance(metadata, dict) else ''}".lower()
        if not any(term in text for term in ("delivery", "deliveries", "inventory", "price cut", "vehicle sales", "交付", "库存", "降价", "销量")):
            continue
        value = number(field_value(point, "value"), None)
        change = _metadata_change(metadata)
        if change is not None:
            scores.append(max(-0.5, min(0.5, change / 20.0)))
        elif value is not None:
            if any(term in text for term in ("beat", "growth", "increase", "record", "above", "strong", "增长", "创新高")):
                scores.append(0.25)
            elif any(term in text for term in ("miss", "decline", "down", "weak", "inventory build", "price cut", "下降", "疲软", "库存增加", "降价")):
                scores.append(-0.25)
    if not scores:
        return None
    return sum(scores) / len(scores)


def _metadata_change(metadata: Any) -> float | None:
    if not isinstance(metadata, dict):
        return None
    for key in ("change_pct", "pct_change", "yoy_change_pct", "qoq_change_pct", "change_percent"):
        if key in metadata:
            return number(metadata.get(key), None)
    return None


def _combine_scores(existing: float, structured: float) -> float:
    if abs(existing) < 0.001:
        return structured
    return existing * 0.7 + structured * 0.3


def _driver_base_weight(driver: str) -> float:
    return {
        DRIVER_FUNDAMENTAL: 0.54,
        DRIVER_DELIVERY: 0.52,
        DRIVER_NARRATIVE: 0.50,
        DRIVER_MACRO: 0.48,
        DRIVER_REGULATORY: 0.50,
        DRIVER_COMPETITION: 0.44,
        DRIVER_ENERGY: 0.40,
        DRIVER_TECHNICAL: 0.42,
        DRIVER_VALUATION: 0.42,
    }.get(driver, 0.40)


def _time_window(text: str) -> str:
    if _has_any_phrase(text, ("robotaxi", "fsd", "ai", "ai chip", "artificial intelligence", "factory", "capacity", "long-term")):
        return "长期"
    if any(term in text for term in ("earnings", "guidance", "quarter", "delivery", "tariff")):
        return "中期"
    return "短期"


def _keyword_sentiment(text: str) -> float:
    positive = sum(1 for term in POSITIVE_TERMS if term in text)
    negative = sum(1 for term in NEGATIVE_TERMS if term in text)
    if positive == negative:
        return 0.0
    return max(-1.0, min(1.0, (positive - negative) / max(positive + negative, 1)))


def _has_any_phrase(text: str, terms: tuple[str, ...]) -> bool:
    return any(_phrase_matches(text, term) for term in terms)


def _phrase_matches(text: str, term: str) -> bool:
    if term == "ai":
        return re.search(r"(?<![a-z0-9])ai(?![a-z0-9])", text) is not None
    return term in text


def _event_relevance(raw_metadata: Any) -> float:
    if not isinstance(raw_metadata, dict):
        return 1.0
    relevance = raw_metadata.get("requested_symbol_relevance")
    if relevance is None:
        relevance = raw_metadata.get("symbol_relevance")
    if relevance is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(relevance)))
    except (TypeError, ValueError):
        return 1.0


def _impact_cap(category: str, text: str, relevance: float, raw_metadata: Any = None) -> float:
    normalized_category = category.lower()
    sec_importance = ""
    if isinstance(raw_metadata, dict):
        sec_importance = str(raw_metadata.get("sec_importance", "")).lower()
    if normalized_category in {"4", "form 4", "144", "s-8", "defa14a", "schedule 13g", "schedule 13g/a"} or sec_importance == "low":
        return 0.26
    if normalized_category in {"schedule 13d", "schedule 13d/a"} or sec_importance == "medium":
        return 0.34
    if normalized_category in {"10-k", "10-k/a", "10-q", "10-q/a"}:
        return 0.52
    if normalized_category in {"8-k", "8-k/a"}:
        if any(term in text for term in ("material", "agreement", "executive", "delivery", "recall", "investigation", "merger", "acquisition", "ceo", "cfo")):
            return 0.58
        return 0.42
    if normalized_category in {"sd"}:
        return 0.42
    if normalized_category in {"filing"}:
        return 0.32
    if relevance < 0.75:
        return 0.55
    if "sec 披露" in text or "仅采集 sec" in text or "raw sec filing metadata collected" in text:
        return 0.36
    return 1.0
