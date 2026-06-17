from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request

from ..config import reliability_for_source
from ..models import CollectionRequest, NewsEvent, PricePoint, SourceRecord, WarningRecord, now_iso
from ..normalization import normalize_symbol, parse_datetime_to_iso, to_float_or_none
from .base import SourceOutput


DEFAULT_NEWS_MIN_RELEVANCE = 0.75
DEFAULT_DIRECT_MATCH_MIN_RELEVANCE = 0.35


class AlphaVantageSource:
    name = "alpha_vantage"
    source_type = "market_data_api"

    def collect(self, request: CollectionRequest) -> SourceOutput:
        output = SourceOutput()
        collected_at = now_iso()
        config = request.data_source_config.get(self.name, {})
        api_key = config.get("api_key") or os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            output.warnings.append(_warning("alpha_vantage_api_key_missing", "ALPHAVANTAGE_API_KEY is missing.", self.name))
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        symbol = request.normalized_symbol
        if "market_data" in request.normalized_requirements:
            try:
                output.market_data.extend(self._fetch_daily_prices(symbol, str(api_key), collected_at))
            except Exception as exc:  # noqa: BLE001
                output.warnings.append(_warning("alpha_vantage_market_failed", f"Alpha Vantage market data failed: {exc}", self.name))

        if "news_events" in request.normalized_requirements:
            try:
                limit = int(config.get("limit", 50))
                output.news_events.extend(self._fetch_news(symbol, str(api_key), limit, collected_at, request.company_name, config))
            except Exception as exc:  # noqa: BLE001
                output.warnings.append(_warning("alpha_vantage_news_failed", f"Alpha Vantage news failed: {exc}", self.name))

        output.source_inventory.append(self._source_record(output, collected_at))
        return output

    def _fetch_daily_prices(self, symbol: str, api_key: str, collected_at: str) -> list[PricePoint]:
        payload = _get_json(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol,
                "outputsize": "compact",
                "apikey": api_key,
            }
        )
        series = payload.get("Time Series (Daily)", {})
        used_function = "TIME_SERIES_DAILY_ADJUSTED"
        if not series and _should_try_free_daily(payload):
            time.sleep(1.2)
            payload = _get_json(
                {
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": "compact",
                    "apikey": api_key,
                }
            )
            series = payload.get("Time Series (Daily)", {})
            used_function = "TIME_SERIES_DAILY"
        if not series:
            raise RuntimeError(_alpha_vantage_error_message(payload))
        prices: list[PricePoint] = []
        for date, row in series.items():
            adjusted_close = to_float_or_none(row.get("5. adjusted close"))
            prices.append(
                PricePoint(
                    date_time=parse_datetime_to_iso(date),
                    open=to_float_or_none(row.get("1. open")),
                    high=to_float_or_none(row.get("2. high")),
                    low=to_float_or_none(row.get("3. low")),
                    close=adjusted_close or to_float_or_none(row.get("4. close")),
                    adjusted_close=adjusted_close,
                    volume=to_float_or_none(row.get("6. volume") or row.get("5. volume")),
                    source="Alpha Vantage",
                    source_reliability=reliability_for_source("Alpha Vantage"),
                    is_adjusted=adjusted_close is not None,
                    collected_at=collected_at,
                    raw_metadata={"row": row, "symbol": normalize_symbol(symbol), "function": used_function},
                )
            )
        return sorted(prices, key=lambda item: item.date_time)

    def _fetch_news(
        self,
        symbol: str,
        api_key: str,
        limit: int,
        collected_at: str,
        company_name: str = "",
        config: dict | None = None,
    ) -> list[NewsEvent]:
        config = config or {}
        aliases = _symbol_aliases(symbol, company_name, config.get("company_aliases"))
        min_relevance = float(config.get("min_relevance", DEFAULT_NEWS_MIN_RELEVANCE))
        direct_min_relevance = float(config.get("direct_match_min_relevance", DEFAULT_DIRECT_MATCH_MIN_RELEVANCE))
        payload = _get_json(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "limit": str(limit),
                "apikey": api_key,
            }
        )
        events: list[NewsEvent] = []
        for item in payload.get("feed", [])[:limit]:
            relevance = _symbol_relevance(item, symbol)
            direct_match = _direct_symbol_match(item, aliases)
            if not _passes_relevance_filter(relevance, direct_match, min_relevance, direct_min_relevance):
                continue
            source = str(item.get("source") or "Alpha Vantage")
            raw_metadata = dict(item)
            raw_metadata.update(
                {
                    "requested_symbol": symbol,
                    "requested_symbol_relevance": relevance.get("relevance_score"),
                    "requested_symbol_sentiment_score": relevance.get("ticker_sentiment_score"),
                    "requested_symbol_sentiment_label": relevance.get("ticker_sentiment_label", ""),
                    "direct_symbol_match": direct_match,
                    "filtered_by_relevance": False,
                    "relevance_filter": {
                        "min_relevance": min_relevance,
                        "direct_match_min_relevance": direct_min_relevance,
                    },
                }
            )
            events.append(
                NewsEvent(
                    title=str(item.get("title", "")),
                    summary_raw=str(item.get("summary", "")),
                    published_at=parse_datetime_to_iso(item.get("time_published")),
                    url=str(item.get("url", "")),
                    publisher=source,
                    source=source,
                    source_reliability=reliability_for_source(source),
                    event_type="news",
                    related_symbols=[symbol],
                    collected_at=collected_at,
                    raw_metadata=raw_metadata,
                )
            )
        return [event for event in events if event.title]

    def _source_record(self, output: SourceOutput, collected_at: str) -> SourceRecord:
        return SourceRecord(
            name=self.name,
            source_type=self.source_type,
            enabled=True,
            used=output.records_collected > 0,
            reliability=reliability_for_source("Alpha Vantage"),
            records_collected=output.records_collected,
            failed=bool(output.warnings) and output.records_collected == 0,
            failure_reason="; ".join(w.message for w in output.warnings),
            collected_at=collected_at,
        )


def _get_json(params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"https://www.alphavantage.co/query?{query}", headers={"User-Agent": "stock-agent-collector/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _should_try_free_daily(payload: dict) -> bool:
    message = " ".join(str(payload.get(key, "")) for key in ("Information", "Note", "Error Message"))
    return "premium endpoint" in message.lower() or bool(message)


def _alpha_vantage_error_message(payload: dict) -> str:
    for key in ("Information", "Note", "Error Message"):
        if payload.get(key):
            return f"Alpha Vantage returned {key}: {payload[key]}"
    return f"Alpha Vantage returned no daily time series. Keys: {sorted(payload.keys())}"


def _passes_relevance_filter(
    relevance: dict[str, float | str | None],
    direct_match: bool,
    min_relevance: float,
    direct_min_relevance: float,
) -> bool:
    score = relevance.get("relevance_score")
    if score is None:
        return False
    if float(score) >= min_relevance:
        return True
    return direct_match and float(score) >= direct_min_relevance


def _symbol_relevance(item: dict, symbol: str) -> dict[str, float | str | None]:
    normalized_symbol = normalize_symbol(symbol)
    for sentiment in item.get("ticker_sentiment", []) or []:
        if normalize_symbol(str(sentiment.get("ticker", ""))) != normalized_symbol:
            continue
        return {
            "relevance_score": to_float_or_none(sentiment.get("relevance_score")),
            "ticker_sentiment_score": to_float_or_none(sentiment.get("ticker_sentiment_score")),
            "ticker_sentiment_label": str(sentiment.get("ticker_sentiment_label", "")),
        }
    return {"relevance_score": None, "ticker_sentiment_score": None, "ticker_sentiment_label": ""}


def _direct_symbol_match(item: dict, aliases: list[str]) -> bool:
    text = " ".join(str(item.get(key, "")) for key in ("title", "summary", "url"))
    return any(_term_matches(text, alias) for alias in aliases)


def _symbol_aliases(symbol: str, company_name: str = "", configured_aliases=None) -> list[str]:
    aliases = [normalize_symbol(symbol)]
    if company_name:
        aliases.extend(_company_name_aliases(company_name))
    if configured_aliases:
        if isinstance(configured_aliases, str):
            aliases.extend(item.strip() for item in configured_aliases.replace("|", ",").split(","))
        else:
            aliases.extend(str(item).strip() for item in configured_aliases)
    return _dedupe([alias for alias in aliases if alias])


def _company_name_aliases(company_name: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", company_name.strip())
    aliases = [cleaned]
    simplified = re.sub(
        r"\b(incorporated|inc|corp|corporation|ltd|limited|plc|co|company|class [a-z])\b\.?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    simplified = re.sub(r"[,.\s]+$", "", re.sub(r"\s+", " ", simplified.replace(",", " "))).strip()
    if simplified and simplified != cleaned:
        aliases.append(simplified)
    return aliases


def _term_matches(text: str, term: str) -> bool:
    cleaned = term.strip()
    if not cleaned:
        return False
    if cleaned.upper() == cleaned and re.fullmatch(r"[A-Z0-9.\-]{1,8}", cleaned):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(cleaned)}(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None

    normalized_text = _normalize_search_text(text)
    normalized_term = _normalize_search_text(cleaned)
    if not normalized_term:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def _normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _warning(code: str, message: str, source: str) -> WarningRecord:
    return WarningRecord(code=code, message=message, source=source, severity="WARNING", collected_at=now_iso())
