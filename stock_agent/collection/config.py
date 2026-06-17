from __future__ import annotations

from typing import Any


DATA_REQUIREMENTS = {
    "market_data",
    "filings",
    "official_events",
    "financial_metrics",
    "news_events",
    "macro_data",
    "industry_data",
    "options_data",
    "broker_account_data",
    "research_reports",
}

REQUIREMENT_TO_RESULT_FIELD = {
    "market_data": "market_data",
    "filings": "filings",
    "official_events": "official_events",
    "financial_metrics": "financial_metrics",
    "news_events": "news_events",
    "macro_data": "macro_data",
    "industry_data": "industry_data",
    "options_data": "options_data",
    "broker_account_data": "broker_account_data",
    "research_reports": "research_reports",
}

SOURCE_ALIASES = {
    "alpha": "alpha_vantage",
    "alphavantage": "alpha_vantage",
    "alpha_vantage": "alpha_vantage",
    "av": "alpha_vantage",
    "sec": "sec_edgar",
    "sec_edgar": "sec_edgar",
    "edgar": "sec_edgar",
    "local": "local",
    "local_file": "local",
    "local_files": "local",
    "fred": "fred",
    "rss": "rss",
    "ib": "ibkr",
    "ibkr": "ibkr",
    "interactive_brokers": "ibkr",
}

DEFAULT_CIK_BY_SYMBOL = {
    "TSLA": "0001318605",
}

DEFAULT_FRED_SERIES = {
    "10Y Treasury Yield": "DGS10",
    "2Y Treasury Yield": "DGS2",
    "Federal Funds Rate": "FEDFUNDS",
    "CPI": "CPIAUCSL",
    "Unemployment Rate": "UNRATE",
}

UNKNOWN_SOURCE_MAX_RELIABILITY = 0.30

SOURCE_RELIABILITY = {
    "sec": 1.00,
    "sec edgar": 1.00,
    "sec_edgar": 1.00,
    "company ir": 1.00,
    "official": 1.00,
    "official filing": 1.00,
    "fred": 0.95,
    "federal reserve": 0.95,
    "bls": 0.95,
    "us treasury": 0.95,
    "treasury": 0.95,
    "ibkr": 0.90,
    "interactive brokers": 0.90,
    "alpha vantage": 0.90,
    "alpha_vantage": 0.90,
    "broker api": 0.90,
    "exchange": 0.90,
    "paid data terminal": 0.80,
    "bloomberg": 0.80,
    "factset": 0.80,
    "reuters": 0.75,
    "bloomberg news": 0.75,
    "wsj": 0.75,
    "wall street journal": 0.75,
    "cnbc": 0.75,
    "yahoo finance": 0.75,
    "yahoo! finance": 0.75,
    "marketwatch": 0.75,
    "seeking alpha": 0.60,
    "benzinga": 0.60,
    "investing.com": 0.60,
    "investing.com canada": 0.60,
    "mainstream financial media": 0.75,
    "industry media": 0.60,
    "rss": 0.60,
    "analyst report": 0.50,
    "research report": 0.50,
    "social media": 0.25,
    "forum": 0.25,
    "rumor": 0.10,
    "sample": 0.10,
}


def normalize_source_key(source: str) -> str:
    cleaned = source.strip().lower().replace("-", "_").replace(" ", "_")
    return SOURCE_ALIASES.get(cleaned, cleaned)


def is_enabled_source(config: dict[str, Any] | None) -> bool:
    if not config:
        return False
    return bool(config.get("enabled", False))


def reliability_for_source(source: str, explicit: float | None = None) -> float:
    key = source.strip().lower().replace("_", " ")
    known = SOURCE_RELIABILITY.get(key) or SOURCE_RELIABILITY.get(source.strip().lower())
    if known is not None:
        if explicit is None:
            return known
        return max(0.0, min(1.0, explicit))
    if explicit is not None:
        return max(0.0, min(UNKNOWN_SOURCE_MAX_RELIABILITY, explicit))
    return UNKNOWN_SOURCE_MAX_RELIABILITY
