from __future__ import annotations

import json
import os
import urllib.request

from tsla_agent.models import ForecastResult, MarketSummary, event_to_dict


def summarize_with_llm(events, market: MarketSummary, forecast: ForecastResult) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not api_key or not model:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an equity research assistant. Summarize evidence, separate facts from inference, "
                    "avoid investment advice, and always discuss uncertainty and downside risks."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Write a concise Chinese Tesla stock research summary.",
                        "market": market.__dict__,
                        "forecast": {
                            "signal": forecast.signal,
                            "rationale": forecast.rationale,
                            "points": [point.__dict__ for point in forecast.points],
                        },
                        "events": [event_to_dict(event) for event in events[:20]],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()
