import json
import os
from typing import List

import requests


def generate_proxy_theses(thesis: str) -> List[str]:
    """
    Generate proxy tradable theses when no close market match exists.
    Uses OpenAI or Gemini if configured, otherwise returns a mock fallback.
    """
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return _generate_openai(thesis)
    if provider == "gemini" and os.getenv("GEMINI_API_KEY"):
        return _generate_gemini(thesis)
    return _generate_mock(thesis)


def _generate_openai(thesis: str) -> List[str]:
    api_key = os.environ["OPENAI_API_KEY"]
    url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    system_prompt = (
        "Given a user thesis with no obvious market matches, propose 3-5 proxy, tradable theses "
        "for Polymarket prediction markets. Be concrete and brief. Output only JSON array of strings."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": thesis},
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return _generate_mock(thesis)


def _generate_gemini(thesis: str) -> List[str]:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = (
        "Given a user thesis with no obvious market matches, propose 3-5 proxy, tradable theses "
        "for Polymarket prediction markets. Be concrete and brief. Output only JSON array of strings.\n\n"
        f"User thesis: {thesis}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return _generate_mock(thesis)


def _generate_mock(thesis: str) -> List[str]:
    return [
        f"{thesis} proxy: US elections impact",
        f"{thesis} proxy: macro rates and CPI",
        f"{thesis} proxy: mega-cap tech sentiment",
    ]
