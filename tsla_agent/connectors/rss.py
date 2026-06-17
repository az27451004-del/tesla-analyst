from __future__ import annotations

import os
import urllib.request
import xml.etree.ElementTree as ET

from tsla_agent.config import AgentConfig
from tsla_agent.connectors.base import CollectionResult
from tsla_agent.models import Event


class RSSConnector:
    name = "rss"

    def collect(self, config: AgentConfig) -> CollectionResult:
        raw_urls = os.getenv("NEWS_RSS_URLS", "")
        urls = [url.strip() for url in raw_urls.split(",") if url.strip()]
        if not urls:
            return CollectionResult(warnings=["NEWS_RSS_URLS 未设置，跳过 RSS 新闻。"])

        result = CollectionResult()
        for url in urls:
            try:
                result.events.extend(self._fetch_feed(url, config.max_events))
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(f"RSS 获取失败 {url}：{exc}")
        return result

    def _fetch_feed(self, url: str, limit: int) -> list[Event]:
        request = urllib.request.Request(url, headers={"User-Agent": "tsla-agent/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()

        root = ET.fromstring(content)
        channel_title = _text(root, ".//channel/title") or url
        events: list[Event] = []

        for item in root.findall(".//item")[:limit]:
            title = _text(item, "title")
            link = _text(item, "link")
            summary = _text(item, "description")
            published = _text(item, "pubDate")
            if title:
                events.append(
                    Event(
                        source=channel_title,
                        title=title,
                        summary=summary,
                        url=link,
                        published_at=published,
                        category="news",
                    )
                )

        if events:
            return events

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        feed_title = _text(root, "atom:title", ns) or channel_title
        for entry in root.findall("atom:entry", ns)[:limit]:
            title = _text(entry, "atom:title", ns)
            summary = _text(entry, "atom:summary", ns) or _text(entry, "atom:content", ns)
            published = _text(entry, "atom:published", ns) or _text(entry, "atom:updated", ns)
            link_node = entry.find("atom:link", ns)
            link = link_node.attrib.get("href", "") if link_node is not None else ""
            if title:
                events.append(
                    Event(
                        source=feed_title,
                        title=title,
                        summary=summary,
                        url=link,
                        published_at=published,
                        category="news",
                    )
                )
        return events


def _text(node: ET.Element, path: str, namespaces: dict[str, str] | None = None) -> str:
    found = node.find(path, namespaces or {})
    if found is None or found.text is None:
        return ""
    return found.text.strip()
