"""Market-state calculations for the second analysis layer."""

from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Any, Iterable

from .models import MarketState, ScenarioForecast
from .utils import field_value, number, round_or_none


def clean_prices(prices: Iterable[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in prices:
        close = number(field_value(item, "close"), None)
        if close is None or close <= 0:
            continue
        date = str(field_value(item, "date", "date_time", default="") or "")
        cleaned.append(
            {
                "date": date,
                "close": close,
                "high": number(field_value(item, "high"), None),
                "low": number(field_value(item, "low"), None),
                "volume": number(field_value(item, "volume"), None),
                "source": str(field_value(item, "source", default="") or ""),
                "raw_metadata": field_value(item, "raw_metadata", default={}) or {},
            }
        )
    return sorted(cleaned, key=lambda item: item["date"])


def build_market_state(symbol: str, prices: list[dict[str, Any]]) -> MarketState:
    normalized_symbol = symbol.upper().strip()
    if not prices:
        return MarketState(symbol=normalized_symbol)

    closes = [float(item["close"]) for item in prices]
    last = prices[-1]
    returns = _daily_returns(closes)
    sma_20 = mean(closes[-20:]) if len(closes) >= 20 else None
    sma_50 = mean(closes[-50:]) if len(closes) >= 50 else None
    vol = stdev(returns) * math.sqrt(252) * 100 if len(returns) >= 2 else None
    recent = prices[-20:]
    support = min(item["low"] if item.get("low") is not None else item["close"] for item in recent)
    resistance = max(item["high"] if item.get("high") is not None else item["close"] for item in recent)
    atr = _atr(prices[-14:])
    return MarketState(
        symbol=normalized_symbol,
        last_close=round(closes[-1], 2),
        last_date=str(last["date"]),
        change_5d_pct=round_or_none(_pct_change(closes, 5)),
        change_20d_pct=round_or_none(_pct_change(closes, 20)),
        annualized_volatility_pct=round_or_none(vol),
        sma_20=round_or_none(sma_20),
        sma_50=round_or_none(sma_50),
        support_level=round(float(support), 2),
        resistance_level=round(float(resistance), 2),
        atr_14=round_or_none(atr),
        trend_label=_trend_label(_pct_change(closes, 20), sma_20, sma_50, closes[-1]),
    )


def build_scenario_forecasts(market: MarketState) -> tuple[ScenarioForecast, ...]:
    if market.last_close is None:
        return ()
    base_band = max((market.annualized_volatility_pct or 35.0) / 100 / math.sqrt(12), 0.04)
    close = market.last_close
    return (
        ScenarioForecast(
            name="Bear Case",
            horizon="1-3 个月",
            price_low=round(close * (1 - base_band * 1.6), 2),
            price_high=round(close * (1 - base_band * 0.5), 2),
            rationale="风险事件、宏观利率或技术趋势恶化时的下行情景。",
            trigger_conditions=("跌破关键支撑", "市场风险偏好走弱", "负面事件被确认"),
        ),
        ScenarioForecast(
            name="Base Case",
            horizon="1-3 个月",
            price_low=round(close * (1 - base_band), 2),
            price_high=round(close * (1 + base_band), 2),
            rationale="当前趋势和波动率延续时的中性区间。",
            trigger_conditions=("价格保持在主要区间内", "无重大新催化剂", "成交量未明显放大"),
        ),
        ScenarioForecast(
            name="Bull Case",
            horizon="1-3 个月",
            price_low=round(close * (1 + base_band * 0.5), 2),
            price_high=round(close * (1 + base_band * 1.6), 2),
            rationale="关键催化剂兑现、趋势改善或市场风险偏好回升时的上行情景。",
            trigger_conditions=("突破关键压力", "正面事件被验证", "宏观环境改善"),
        ),
    )


def _daily_returns(closes: list[float]) -> list[float]:
    return [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes)) if closes[index - 1] > 0]


def _pct_change(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or closes[-days - 1] <= 0:
        return None
    return (closes[-1] / closes[-days - 1] - 1) * 100


def _atr(prices: list[dict[str, Any]]) -> float | None:
    ranges = [
        float(item["high"]) - float(item["low"])
        for item in prices
        if item.get("high") is not None and item.get("low") is not None and item["high"] >= item["low"]
    ]
    return mean(ranges) if ranges else None


def _trend_label(change_20d: float | None, sma_20: float | None, sma_50: float | None, last_close: float) -> str:
    if sma_20 is not None and sma_50 is not None:
        if last_close > sma_20 > sma_50:
            return "多头趋势"
        if last_close < sma_20 < sma_50:
            return "空头趋势"
    if change_20d is not None:
        if change_20d > 5:
            return "短中期偏强"
        if change_20d < -5:
            return "短中期偏弱"
    return "震荡/中性"
