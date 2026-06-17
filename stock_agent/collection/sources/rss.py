from __future__ import annotations

from dataclasses import dataclass
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from ..config import reliability_for_source
from ..models import CollectionRequest, NewsEvent, SourceRecord, WarningRecord, now_iso
from ..normalization import normalize_symbol, parse_datetime_to_iso
from .base import SourceOutput


DEFAULT_FEED_TEMPLATES = (
    {
        "name": "google_news",
        "url": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "yahoo_finance",
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
    },
    {
        "name": "seeking_alpha",
        "url": "https://seekingalpha.com/api/sa/combined/{symbol}.xml",
    },
)


@dataclass(frozen=True)
class FeedRequest:
    url: str
    query_symbol: str = ""
    template_name: str = "static"
    generated: bool = False


class RSSSource:
    name = "rss"
    source_type = "user_configured_rss"

    def collect(self, request: CollectionRequest) -> SourceOutput:
        output = SourceOutput()
        collected_at = now_iso()
        config = request.data_source_config.get(self.name, {})

        if "news_events" not in request.normalized_requirements:
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        symbols = _symbols_from_config(config, request.normalized_symbol)
        aliases = _company_aliases_from_config(config, symbols, request)
        feed_requests = _build_feed_requests(
            symbols=symbols,
            aliases_by_symbol=aliases,
            static_urls=_urls_from_config(config.get("urls")),
            feed_templates=_feed_templates_from_config(config),
        )
        if not feed_requests:
            output.warnings.append(_warning("rss_urls_missing", "No RSS URLs configured.", self.name))
            output.source_inventory.append(self._source_record(output, collected_at))
            return output

        limit = int(config.get("limit", 30))
        for feed in feed_requests:
            try:
                output.news_events.extend(self._fetch_feed(feed, symbols, aliases, limit, collected_at))
            except Exception as exc:  # noqa: BLE001
                output.warnings.append(_warning("rss_fetch_failed", f"RSS fetch failed for {feed.url}: {exc}", self.name))

        output.source_inventory.append(self._source_record(output, collected_at, symbols, feed_requests))
        return output

    def _fetch_feed(
        self,
        feed: FeedRequest,
        symbols: list[str],
        aliases_by_symbol: dict[str, list[str]],
        limit: int,
        collected_at: str,
    ) -> list[NewsEvent]:
        request = urllib.request.Request(feed.url, headers={"User-Agent": "stock-agent-collector/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
        root = ET.fromstring(content)
        events = _parse_rss(root, feed, limit, collected_at)
        if events:
            return _filter_and_tag_events(events, symbols, aliases_by_symbol, feed)
        return _filter_and_tag_events(_parse_atom(root, feed, limit, collected_at), symbols, aliases_by_symbol, feed)

    def _source_record(
        self,
        output: SourceOutput,
        collected_at: str,
        symbols: list[str] | None = None,
        feeds: list[FeedRequest] | None = None,
    ) -> SourceRecord:
        feeds = feeds or []
        return SourceRecord(
            name=self.name,
            source_type=self.source_type,
            enabled=True,
            used=output.records_collected > 0,
            reliability=reliability_for_source("RSS"),
            records_collected=output.records_collected,
            failed=bool(output.warnings) and output.records_collected == 0,
            failure_reason="; ".join(w.message for w in output.warnings),
            collected_at=collected_at,
            raw_metadata={
                "symbols": symbols or [],
                "generated_feed_count": sum(1 for feed in feeds if feed.generated),
                "static_feed_count": sum(1 for feed in feeds if not feed.generated),
            },
        )


def _parse_rss(root: ET.Element, feed: FeedRequest, limit: int, collected_at: str) -> list[NewsEvent]:
    channel_title = _text(root, ".//channel/title") or feed.url
    events: list[NewsEvent] = []
    for item in root.findall(".//item")[:limit]:
        raw_title = _text(item, "title")
        title, source = _title_and_source(raw_title, channel_title, feed)
        if not title:
            continue
        events.append(
            NewsEvent(
                title=title,
                summary_raw=_text(item, "description"),
                published_at=parse_datetime_to_iso(_text(item, "pubDate")),
                url=_text(item, "link"),
                publisher=source,
                source=source,
                source_reliability=reliability_for_source(source),
                event_type="news",
                related_symbols=[],
                collected_at=collected_at,
                raw_metadata={
                    "feed_url": feed.url,
                    "feed_title": channel_title,
                    "raw_title": raw_title,
                    "query_symbol": feed.query_symbol,
                    "template_name": feed.template_name,
                    "generated_feed": feed.generated,
                },
            )
        )
    return events


def _parse_atom(root: ET.Element, feed: FeedRequest, limit: int, collected_at: str) -> list[NewsEvent]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    feed_title = _text(root, "atom:title", ns) or feed.url
    events: list[NewsEvent] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        raw_title = _text(entry, "atom:title", ns)
        title, source = _title_and_source(raw_title, feed_title, feed)
        if not title:
            continue
        link_node = entry.find("atom:link", ns)
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        events.append(
            NewsEvent(
                title=title,
                summary_raw=_text(entry, "atom:summary", ns) or _text(entry, "atom:content", ns),
                published_at=parse_datetime_to_iso(_text(entry, "atom:published", ns) or _text(entry, "atom:updated", ns)),
                url=link,
                publisher=source,
                source=source,
                source_reliability=reliability_for_source(source),
                event_type="news",
                related_symbols=[],
                collected_at=collected_at,
                raw_metadata={
                    "feed_url": feed.url,
                    "feed_title": feed_title,
                    "raw_title": raw_title,
                    "query_symbol": feed.query_symbol,
                    "template_name": feed.template_name,
                    "generated_feed": feed.generated,
                },
            )
        )
    return events


def _filter_and_tag_events(
    events: list[NewsEvent],
    symbols: list[str],
    aliases_by_symbol: dict[str, list[str]],
    feed: FeedRequest,
) -> list[NewsEvent]:
    filtered: list[NewsEvent] = []
    for event in events:
        matched_symbols, matched_terms = _match_event_symbols(event, symbols, aliases_by_symbol)
        if not matched_symbols:
            continue
        direct_symbol_match = _direct_symbol_match(matched_symbols, matched_terms, aliases_by_symbol)
        event.related_symbols = matched_symbols
        event.raw_metadata = {
            **event.raw_metadata,
            "feed_url": feed.url,
            "matched_symbols": matched_symbols,
            "matched_terms": matched_terms,
            "direct_symbol_match": direct_symbol_match,
            "match_type": "direct_symbol" if direct_symbol_match else "indirect_related",
            "query_symbol": feed.query_symbol,
        }
        filtered.append(event)
    return filtered


def _match_event_symbols(
    event: NewsEvent,
    symbols: list[str],
    aliases_by_symbol: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    text = " ".join([event.title, event.summary_raw, event.url])
    matched_symbols: list[str] = []
    matched_terms: list[str] = []
    for symbol in symbols:
        terms = _match_terms_for_symbol(symbol, aliases_by_symbol)
        symbol_matches = [term for term in terms if _term_matches(text, term)]
        if not symbol_matches:
            continue
        matched_symbols.append(symbol)
        matched_terms.extend(term for term in symbol_matches if term not in matched_terms)
    return matched_symbols, matched_terms


def _match_terms_for_symbol(symbol: str, aliases_by_symbol: dict[str, list[str]]) -> list[str]:
    return _dedupe([symbol, *aliases_by_symbol.get(symbol, [])])


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


def _title_and_source(raw_title: str, feed_title: str, feed: FeedRequest) -> tuple[str, str]:
    source = _source_from_feed_title(feed_title)
    title = raw_title.strip()
    if _is_google_news_feed(feed, feed_title):
        title, source = _split_google_news_source(title, source)
    return title, source


def _is_google_news_feed(feed: FeedRequest, feed_title: str) -> bool:
    return "news.google.com" in feed.url.lower() or "google news" in feed_title.lower()


def _split_google_news_source(title: str, fallback_source: str) -> tuple[str, str]:
    if " - " not in title:
        return title, fallback_source
    headline, suffix = title.rsplit(" - ", 1)
    source = suffix.strip()
    if not headline.strip() or not source:
        return title, fallback_source
    return headline.strip(), _source_from_feed_title(source)


def _source_from_feed_title(feed_title: str) -> str:
    cleaned = re.sub(r"\s+", " ", feed_title.strip())
    lowered = cleaned.lower()
    if "yahoo" in lowered and "finance" in lowered:
        return "Yahoo Finance"
    if "seeking alpha" in lowered:
        return "Seeking Alpha"
    if "marketwatch" in lowered:
        return "MarketWatch"
    if "investing.com" in lowered:
        return "Investing.com"
    if cleaned:
        return cleaned
    return "RSS"


def _direct_symbol_match(
    matched_symbols: list[str],
    matched_terms: list[str],
    aliases_by_symbol: dict[str, list[str]],
) -> bool:
    normalized_terms = {_normalize_search_text(term) for term in matched_terms}
    for symbol in matched_symbols:
        for term in _match_terms_for_symbol(symbol, aliases_by_symbol):
            if _normalize_search_text(term) in normalized_terms:
                return True
    return False


def _symbols_from_config(config: dict[str, Any], default_symbol: str) -> list[str]:
    raw_symbols = config.get("symbols")
    if raw_symbols is None:
        return [default_symbol] if default_symbol else []
    if isinstance(raw_symbols, str):
        raw_items = raw_symbols.split(",")
    else:
        raw_items = list(raw_symbols)
    symbols = [normalize_symbol(str(item)) for item in raw_items if str(item).strip()]
    return _dedupe(symbols)


def _company_aliases_from_config(
    config: dict[str, Any],
    symbols: list[str],
    request: CollectionRequest,
) -> dict[str, list[str]]:
    raw_aliases = config.get("company_aliases") or {}
    aliases: dict[str, list[str]] = {symbol: [] for symbol in symbols}
    if isinstance(raw_aliases, dict):
        for raw_symbol, raw_values in raw_aliases.items():
            symbol = normalize_symbol(str(raw_symbol))
            if symbol not in aliases:
                continue
            aliases[symbol].extend(_alias_list(raw_values))
    if request.normalized_symbol in aliases and request.company_name:
        aliases[request.normalized_symbol].append(request.company_name)
    return {symbol: _dedupe(items) for symbol, items in aliases.items()}


def _alias_list(raw_values: Any) -> list[str]:
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        separators = "|" if "|" in raw_values else ","
        return [item.strip() for item in raw_values.split(separators) if item.strip()]
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _urls_from_config(raw_urls: Any) -> list[str]:
    if raw_urls is None:
        return []
    if isinstance(raw_urls, str):
        return [url.strip() for url in raw_urls.split(",") if url.strip()]
    return [str(url).strip() for url in raw_urls if str(url).strip()]


def _feed_templates_from_config(config: dict[str, Any]) -> list[dict[str, str]]:
    if "feed_templates" not in config:
        return [dict(item) for item in DEFAULT_FEED_TEMPLATES]
    raw_templates = config.get("feed_templates")
    if raw_templates in (None, False):
        return []
    if isinstance(raw_templates, str):
        raw_items: list[Any] = [item.strip() for item in raw_templates.split(",") if item.strip()]
    else:
        raw_items = list(raw_templates)

    templates: list[dict[str, str]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("template") or "").strip()
            name = str(item.get("name") or f"custom_{index + 1}").strip()
        else:
            url = str(item).strip()
            name = f"custom_{index + 1}"
        if url:
            templates.append({"name": name, "url": url})
    return templates


def _build_feed_requests(
    *,
    symbols: list[str],
    aliases_by_symbol: dict[str, list[str]],
    static_urls: list[str],
    feed_templates: list[dict[str, str]],
) -> list[FeedRequest]:
    feeds: list[FeedRequest] = []
    for symbol in symbols:
        query = _query_for_symbol(symbol, aliases_by_symbol.get(symbol, []))
        for template in feed_templates:
            url_template = template["url"]
            feeds.append(
                FeedRequest(
                    url=_format_feed_url(url_template, symbol, query),
                    query_symbol=symbol,
                    template_name=template.get("name", "custom"),
                    generated=True,
                )
            )
    feeds.extend(FeedRequest(url=url) for url in static_urls)
    return _dedupe_feed_requests(feeds)


def _format_feed_url(url_template: str, symbol: str, query: str) -> str:
    return url_template.format(
        symbol=urllib.parse.quote(symbol, safe=""),
        symbol_raw=symbol,
        query=urllib.parse.quote(query, safe=""),
        query_plus=urllib.parse.quote_plus(query),
        query_raw=query,
    )


def _query_for_symbol(symbol: str, aliases: list[str]) -> str:
    terms = _dedupe([symbol, *aliases])
    expression = " OR ".join(_quote_query_term(term) for term in terms)
    if not expression:
        return "stock"
    return f"({expression}) stock"


def _quote_query_term(term: str) -> str:
    cleaned = term.strip()
    if " " in cleaned:
        return f'"{cleaned}"'
    return cleaned


def _dedupe_feed_requests(feeds: list[FeedRequest]) -> list[FeedRequest]:
    seen: set[tuple[str, str]] = set()
    result: list[FeedRequest] = []
    for feed in feeds:
        key = (feed.url, feed.query_symbol)
        if key in seen:
            continue
        seen.add(key)
        result.append(feed)
    return result


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _text(node: ET.Element, path: str, namespaces: dict[str, str] | None = None) -> str:
    found = node.find(path, namespaces or {})
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _warning(code: str, message: str, source: str) -> WarningRecord:
    return WarningRecord(code=code, message=message, source=source, severity="WARNING", collected_at=now_iso())
