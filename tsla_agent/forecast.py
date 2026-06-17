from __future__ import annotations

import math
from statistics import mean, stdev

from tsla_agent.models import ForecastPoint, ForecastResult, MarketSummary, PricePoint


def summarize_market(symbol: str, prices: list[PricePoint]) -> MarketSummary:
    ordered = _clean_prices(prices)
    if not ordered:
        return MarketSummary(symbol, None, "", None, None, None, None, None, "无价格数据")

    closes = [item.close for item in ordered]
    last = ordered[-1]
    change_5d = _pct_change(closes, 5)
    change_20d = _pct_change(closes, 20)
    returns = _daily_returns(closes)
    annualized_vol = stdev(returns) * math.sqrt(252) * 100 if len(returns) >= 2 else None
    sma_20 = mean(closes[-20:]) if len(closes) >= 20 else None
    sma_50 = mean(closes[-50:]) if len(closes) >= 50 else None
    trend = _trend_label(change_20d, sma_20, sma_50, last.close)
    return MarketSummary(
        symbol=symbol,
        last_close=round(last.close, 2),
        last_date=last.date,
        change_5d_pct=_round_or_none(change_5d),
        change_20d_pct=_round_or_none(change_20d),
        annualized_volatility_pct=_round_or_none(annualized_vol),
        sma_20=_round_or_none(sma_20),
        sma_50=_round_or_none(sma_50),
        trend_label=trend,
    )


def forecast_price_path(
    prices: list[PricePoint],
    event_sentiment_tilt: float = 0.0,
    horizons: tuple[int, ...] = (1, 5, 20),
) -> ForecastResult:
    ordered = _clean_prices(prices)
    if len(ordered) < 6:
        return ForecastResult(
            signal="数据不足",
            rationale="价格历史少于 6 个交易日，无法形成可靠的动量和波动率估计。",
            points=(),
        )

    closes = [item.close for item in ordered]
    returns = _daily_returns(closes)
    short_momentum = mean(returns[-5:])
    medium_momentum = mean(returns[-20:]) if len(returns) >= 20 else mean(returns)
    volatility = stdev(returns[-60:]) if len(returns[-60:]) >= 2 else stdev(returns)

    sentiment_adjustment = max(-0.004, min(0.004, event_sentiment_tilt * 0.004))
    daily_drift = 0.45 * short_momentum + 0.55 * medium_momentum + sentiment_adjustment
    daily_drift = max(-0.03, min(0.03, daily_drift))

    last_close = closes[-1]
    points: list[ForecastPoint] = []
    for days in horizons:
        expected = last_close * ((1 + daily_drift) ** days)
        band = max(0.01, volatility * math.sqrt(days))
        points.append(
            ForecastPoint(
                horizon_days=days,
                base_price=round(expected, 2),
                bull_price=round(expected * (1 + band), 2),
                bear_price=round(expected * (1 - band), 2),
                expected_return_pct=round((expected / last_close - 1) * 100, 2),
                confidence_band_pct=round(band * 100, 2),
            )
        )

    signal = _signal_from_drift(daily_drift, volatility)
    rationale = (
        f"短期动量 {short_momentum * 100:.2f}%/日，中期动量 {medium_momentum * 100:.2f}%/日，"
        f"事件情绪修正 {sentiment_adjustment * 100:.2f}%/日，日波动率约 {volatility * 100:.2f}%。"
    )
    return ForecastResult(signal=signal, rationale=rationale, points=tuple(points))


def weighted_event_sentiment(events) -> float:
    if not events:
        return 0.0
    weight_sum = sum(max(event.impact_score, 0.05) for event in events)
    if weight_sum == 0:
        return 0.0
    return sum(event.sentiment * max(event.impact_score, 0.05) for event in events) / weight_sum


def _clean_prices(prices: list[PricePoint]) -> list[PricePoint]:
    return sorted([price for price in prices if price.close > 0], key=lambda item: item.date)


def _daily_returns(closes: list[float]) -> list[float]:
    return [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes)) if closes[index - 1] > 0]


def _pct_change(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or closes[-days - 1] <= 0:
        return None
    return (closes[-1] / closes[-days - 1] - 1) * 100


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


def _signal_from_drift(drift: float, volatility: float) -> str:
    if drift > max(0.001, volatility * 0.18):
        return "偏多"
    if drift < -max(0.001, volatility * 0.18):
        return "偏空"
    return "震荡"


def _round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None
