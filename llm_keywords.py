import json
import os
from typing import List

import requests


def generate_keywords(query: str) -> List[str]:
    """
    Generate search keywords from a thesis using Gemini or fallback.
    """
    if os.getenv("GEMINI_API_KEY"):
        return _generate_with_gemini(query)
    return _generate_mock(query)


def _generate_with_gemini(query: str) -> List[str]:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = (
        "Given the user query, output a JSON array of 3-6 SHORT search keywords (1-2 words each) "
        "to find relevant prediction markets in a database. Keep keywords simple for substring matching.\n\n"
        "IMPORTANT: Keywords must stay specific to the main subject. Don't use generic terms alone.\n"
        "- GOOD: 'Trump election', 'Trump president' (tied to subject)\n"
        "- BAD: 'election', 'president' (too generic, could match anything)\n\n"
        "Examples:\n"
        "- 'Lakers good season' -> [\"Lakers\", \"Lakers championship\", \"Lakers playoff\", \"LeBron Lakers\"]\n"
        "- 'Trump wins election' -> [\"Trump\", \"Trump election\", \"Trump president\", \"Trump 2024\"]\n"
        "- 'Bitcoin above 100k' -> [\"Bitcoin\", \"Bitcoin price\", \"BTC\", \"Bitcoin 100000\"]\n\n"
        "Output only JSON array of strings.\n"
        f"User query: {query}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return _generate_mock(query)


def _generate_mock(query: str) -> List[str]:
    parts = [p.strip() for p in query.replace(",", " ").split() if len(p.strip()) > 3]
    dedup = []
    for p in parts:
        if p.lower() not in dedup:
            dedup.append(p.lower())
    return dedup[:6] if dedup else [query]
