import unittest
from unittest.mock import patch

from stock_agent.cli import _build_collection_request, build_parser
from stock_agent.collection import CollectionRequest, collect_data
from stock_agent.collection.models import NewsEvent
from stock_agent.collection.sources.rss import (
    _build_feed_requests,
    _feed_templates_from_config,
    _match_event_symbols,
)


class RSSCollectionTest(unittest.TestCase):
    def test_builds_default_symbol_feeds_and_keeps_static_urls(self):
        feeds = _build_feed_requests(
            symbols=["TSLA"],
            aliases_by_symbol={"TSLA": ["Tesla", "Tesla Inc"]},
            static_urls=["https://example.test/static.xml"],
            feed_templates=_feed_templates_from_config({}),
            topic_queries=["Strait of Hormuz"],
        )
        urls = [feed.url for feed in feeds]

        self.assertTrue(any("news.google.com" in url for url in urls))
        self.assertTrue(any("feeds.finance.yahoo.com" in url and "TSLA" in url for url in urls))
        self.assertTrue(any("seekingalpha.com" in url and "TSLA" in url for url in urls))
        self.assertTrue(any("Hormuz" in url for url in urls))
        self.assertIn("https://example.test/static.xml", urls)

    def test_cli_builds_multi_symbol_rss_config(self):
        args = build_parser().parse_args(
            [
                "collect",
                "--symbol",
                "TSLA",
                "--requirements",
                "news_events",
                "--output",
                "/tmp/out.json",
                "--rss-symbols",
                "TSLA,AAPL,NVDA",
                "--rss-alias",
                "TSLA=Tesla|Tesla Inc",
                "--rss-alias",
                "AAPL=Apple|Apple Inc",
                "--rss-url",
                "https://example.test/static.xml",
                "--rss-topic-query",
                "Strait of Hormuz",
            ]
        )

        request = _build_collection_request(args)
        rss_config = request.data_source_config["rss"]

        self.assertEqual(rss_config["symbols"], ["TSLA", "AAPL", "NVDA"])
        self.assertEqual(rss_config["company_aliases"]["TSLA"], ["Tesla", "Tesla Inc"])
        self.assertEqual(rss_config["company_aliases"]["AAPL"], ["Apple", "Apple Inc"])
        self.assertEqual(rss_config["urls"], ["https://example.test/static.xml"])
        self.assertEqual(rss_config["topic_queries"], ["Strait of Hormuz"])

    def test_matches_news_to_symbols_with_aliases(self):
        aliases = {"TSLA": ["Tesla", "Tesla Inc"], "AAPL": ["Apple", "Apple Inc"], "NVDA": ["Nvidia", "NVIDIA Corp"]}

        tesla_event = NewsEvent(title="Tesla expands robotaxi testing", summary_raw="", url="")
        apple_event = NewsEvent(title="Apple shares rise after services update", summary_raw="", url="")
        broad_event = NewsEvent(title="Stocks rise as broader market advances", summary_raw="", url="")
        multi_event = NewsEvent(title="Tesla and Nvidia partner on AI infrastructure", summary_raw="", url="")

        self.assertEqual(_match_event_symbols(tesla_event, ["TSLA", "AAPL", "NVDA"], aliases)[0], ["TSLA"])
        self.assertEqual(_match_event_symbols(apple_event, ["TSLA", "AAPL", "NVDA"], aliases)[0], ["AAPL"])
        self.assertEqual(_match_event_symbols(broad_event, ["TSLA", "AAPL", "NVDA"], aliases)[0], [])
        self.assertEqual(_match_event_symbols(multi_event, ["TSLA", "AAPL", "NVDA"], aliases)[0], ["TSLA", "NVDA"])

    def test_collect_data_reads_generated_multi_symbol_rss(self):
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["news_events"],
            data_source_config={
                "rss": {
                    "enabled": True,
                    "symbols": ["TSLA", "AAPL"],
                    "company_aliases": {"TSLA": ["Tesla"], "AAPL": ["Apple"]},
                    "feed_templates": ["https://example.test/{symbol}.xml"],
                    "limit": 5,
                }
            },
        )

        with patch("stock_agent.collection.sources.rss.urllib.request.urlopen", side_effect=_fake_urlopen):
            result = collect_data(request)

        titles = {event.title for event in result.news_events}
        self.assertIn("Tesla announces delivery update", titles)
        self.assertIn("Apple reports services growth", titles)
        self.assertNotIn("Stocks rise as broader market advances", titles)
        self.assertTrue(result.source_inventory[-1].used)
        self.assertEqual(result.source_inventory[-1].raw_metadata["generated_feed_count"], 2)

        tesla = next(event for event in result.news_events if event.title == "Tesla announces delivery update")
        self.assertEqual(tesla.related_symbols, ["TSLA"])
        self.assertEqual(tesla.raw_metadata["matched_symbols"], ["TSLA"])
        self.assertEqual(tesla.raw_metadata["query_symbol"], "TSLA")

        serialized = result.to_json()
        self.assertNotIn("buy_signal", serialized)
        self.assertNotIn("sell_signal", serialized)
        self.assertNotIn("trade_plan", serialized)
        self.assertNotIn("generated_target_price", serialized)

    def test_collect_data_keeps_market_topic_events_without_symbol_match(self):
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["news_events"],
            data_source_config={
                "rss": {
                    "enabled": True,
                    "symbols": ["TSLA"],
                    "company_aliases": {"TSLA": ["Tesla"]},
                    "topic_queries": ["Strait of Hormuz"],
                    "feed_templates": ["https://example.test/{query}.xml"],
                    "limit": 5,
                }
            },
        )

        with patch("stock_agent.collection.sources.rss.urllib.request.urlopen", side_effect=_fake_topic_urlopen):
            result = collect_data(request)

        titles = {event.title for event in result.news_events}
        self.assertIn("Strait of Hormuz reopens as oil shipping resumes", titles)
        topic_event = next(event for event in result.news_events if event.title == "Strait of Hormuz reopens as oil shipping resumes")
        self.assertEqual(topic_event.raw_metadata["match_type"], "market_theme")
        self.assertTrue(topic_event.raw_metadata["market_wide_event"])
        self.assertEqual(topic_event.raw_metadata["market_topic_query"], "Strait of Hormuz")
        self.assertAlmostEqual(topic_event.raw_metadata["requested_symbol_relevance"], 0.38)

    def test_static_rss_url_still_collects_matching_items(self):
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["news_events"],
            data_source_config={
                "rss": {
                    "enabled": True,
                    "urls": ["https://example.test/static.xml"],
                    "company_aliases": {"TSLA": ["Tesla"]},
                    "feed_templates": [],
                    "limit": 5,
                }
            },
        )

        with patch("stock_agent.collection.sources.rss.urllib.request.urlopen", side_effect=_fake_urlopen):
            result = collect_data(request)

        self.assertEqual(len(result.news_events), 1)
        self.assertEqual(result.news_events[0].title, "Tesla announces delivery update")
        self.assertEqual(result.source_inventory[-1].raw_metadata["static_feed_count"], 1)

    def test_google_news_item_uses_original_publisher_source(self):
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["news_events"],
            data_source_config={
                "rss": {
                    "enabled": True,
                    "urls": ["https://news.google.com/rss/search?q=Tesla"],
                    "company_aliases": {"TSLA": ["Tesla"]},
                    "feed_templates": [],
                    "limit": 5,
                }
            },
        )

        with patch("stock_agent.collection.sources.rss.urllib.request.urlopen", side_effect=_fake_google_urlopen):
            result = collect_data(request)

        self.assertEqual(len(result.news_events), 1)
        event = result.news_events[0]
        self.assertEqual(event.title, "Tesla expands robotaxi testing")
        self.assertEqual(event.source, "Reuters")
        self.assertEqual(event.source_reliability, 0.75)
        self.assertEqual(event.raw_metadata["raw_title"], "Tesla expands robotaxi testing - Reuters")

    def test_rss_failure_warns_without_aborting_collection(self):
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["news_events"],
            data_source_config={
                "rss": {
                    "enabled": True,
                    "urls": ["https://example.test/fail.xml"],
                    "feed_templates": [],
                }
            },
        )

        with patch("stock_agent.collection.sources.rss.urllib.request.urlopen", side_effect=RuntimeError("boom")):
            result = collect_data(request)

        self.assertEqual(result.news_events, [])
        self.assertIn("rss_fetch_failed", {warning.code for warning in result.warnings})
        self.assertTrue(result.source_inventory[-1].failed)


class _FakeResponse:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def _fake_urlopen(request, timeout=30):
    url = request.full_url
    if "AAPL" in url:
        return _FakeResponse(
            _rss_xml(
                [
                    ("Apple reports services growth", "Apple revenue update", "https://example.test/apple"),
                    ("Stocks rise as broader market advances", "No single stock mentioned", "https://example.test/broad"),
                ]
            )
        )
    if "fail" in url:
        raise RuntimeError("boom")
    return _FakeResponse(
        _rss_xml(
            [
                ("Tesla announces delivery update", "Tesla production summary", "https://example.test/tesla"),
                ("Stocks rise as broader market advances", "No single stock mentioned", "https://example.test/broad"),
            ]
        )
    )


def _fake_google_urlopen(request, timeout=30):
    return _FakeResponse(
        _rss_xml(
            [
                ("Tesla expands robotaxi testing - Reuters", "Tesla production summary", "https://example.test/tesla"),
                ("Stocks rise as broader market advances - Reuters", "No single stock mentioned", "https://example.test/broad"),
            ],
            channel_title='"Tesla" - Google News',
        )
    )


def _fake_topic_urlopen(request, timeout=30):
    return _FakeResponse(
        _rss_xml(
            [
                ("Strait of Hormuz reopens as oil shipping resumes", "Oil supply risk eases after talks", "https://example.test/hormuz"),
                ("Stocks rise as broader market advances", "No topic match needed because feed is market-wide", "https://example.test/broad"),
            ],
            channel_title='"Strait of Hormuz" - Google News',
        )
    )


def _rss_xml(items, channel_title="Mock RSS"):
    body = "".join(
        f"<item><title>{title}</title><description>{description}</description><link>{url}</link><pubDate>Mon, 15 Jun 2026 12:00:00 GMT</pubDate></item>"
        for title, description, url in items
    )
    return f"<?xml version='1.0'?><rss><channel><title>{channel_title}</title>{body}</channel></rss>"


if __name__ == "__main__":
    unittest.main()
