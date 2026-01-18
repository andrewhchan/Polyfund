import json
import os
from typing import List

import requests


def generate_proxy_theses(thesis: str) -> List[str]:
    """
    Generate exactly 5 alternative proxy tradable theses when no close market match exists.
    Uses Gemini if configured, otherwise returns a mock fallback.
    """
    if os.getenv("GEMINI_API_KEY"):
        return _generate_gemini(thesis)
    return _generate_mock(thesis)


def _generate_gemini(thesis: str) -> List[str]:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = (
        "Given a user thesis with no obvious market matches, propose exactly 5 alternative proxy theses "
        "that could be searched on Polymarket prediction markets. These should be related but different angles "
        "or adjacent topics that might have tradable markets. Be concrete and specific. "
        "Output only a JSON array of exactly 5 strings.\n\n"
        f"User thesis: {thesis}"
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
            result = [str(x) for x in parsed]
            # Ensure exactly 5 results
            if len(result) >= 5:
                return result[:5]
            # Pad if fewer than 5
            while len(result) < 5:
                result.append(f"{thesis} - alternative {len(result) + 1}")
            return result
    except Exception:
        pass
    return _generate_mock(thesis)


def _generate_mock(thesis: str) -> List[str]:
    return [
        f"{thesis} proxy: US elections impact",
        f"{thesis} proxy: macro rates and CPI",
        f"{thesis} proxy: mega-cap tech sentiment",
        f"{thesis} proxy: sports betting correlation",
        f"{thesis} proxy: geopolitical events",
    ]
