from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from tsla_agent.config import AgentConfig
from tsla_agent.connectors.base import CollectionResult
from tsla_agent.models import Event, PricePoint


class AlphaVantageConnector:
    name = "alpha_vantage"

    def collect(self, config: AgentConfig) -> CollectionResult:
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            return CollectionResult(warnings=["ALPHAVANTAGE_API_KEY 未设置，跳过 Alpha Vantage 行情/新闻。"])

        result = CollectionResult()
        symbol = config.normalized_symbol
        try:
            result.prices.extend(self._fetch_daily_prices(symbol, api_key))
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Alpha Vantage 行情获取失败：{exc}")

        try:
            result.events.extend(self._fetch_news(symbol, api_key, config.max_events))
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Alpha Vantage 新闻获取失败：{exc}")
        return result

    def _fetch_daily_prices(self, symbol: str, api_key: str) -> list[PricePoint]:
        payload = _get_json(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol,
                "outputsize": "compact",
                "apikey": api_key,
            }
        )
        series = payload.get("Time Series (Daily)", {})
        prices: list[PricePoint] = []
        for date, row in series.items():
            prices.append(
                PricePoint(
                    date=date,
                    open=_float(row.get("1. open")),
                    high=_float(row.get("2. high")),
                    low=_float(row.get("3. low")),
                    close=_float(row.get("5. adjusted close") or row.get("4. close")),
                    volume=_float(row.get("6. volume")),
                )
            )
        return sorted(prices, key=lambda item: item.date)

    def _fetch_news(self, symbol: str, api_key: str, limit: int) -> list[Event]:
        payload = _get_json(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "limit": str(limit),
                "apikey": api_key,
            }
        )
        events: list[Event] = []
        for item in payload.get("feed", [])[:limit]:
            ticker_score = 0.0
            for ticker in item.get("ticker_sentiment", []):
                if ticker.get("ticker") == symbol:
                    ticker_score = _float(ticker.get("ticker_sentiment_score"))
                    break
            events.append(
                Event(
                    source=str(item.get("source", "Alpha Vantage")),
                    title=str(item.get("title", "")),
                    summary=str(item.get("summary", "")),
                    url=str(item.get("url", "")),
                    published_at=str(item.get("time_published", "")),
                    category="news",
                    sentiment=ticker_score or _float(item.get("overall_sentiment_score")),
                    tags=tuple(str(topic.get("topic", "")) for topic in item.get("topics", []) if topic.get("topic")),
                    raw=dict(item),
                )
            )
        return [event for event in events if event.title]


def _get_json(params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"https://www.alphavantage.co/query?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "tsla-agent/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
