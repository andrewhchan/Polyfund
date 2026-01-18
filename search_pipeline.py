from typing import Dict, List, Tuple, Any

from rapidfuzz import fuzz

from llm_keywords import generate_keywords
from market_data import search_polymarket_events
from llm_proxy import generate_proxy_theses

KEYWORD_MATCH_THRESHOLD = 70


def discover_markets(
    query: str,
    k: int = 30,
    keyword_match_threshold: int = KEYWORD_MATCH_THRESHOLD,
    allow_fallback: bool = True
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    keywords = generate_keywords(query)
    seen = {}
    explain_filters = {"deduped": 0, "total_found": 0, "skipped_non_dict": 0}
    scored = []

    for kw in keywords:
        try:
            events = search_polymarket_events(kw, limit=k)
        except Exception:
            continue

        for event in events or []:
            if not isinstance(event, dict):
                explain_filters["skipped_non_dict"] += 1
                continue
            markets = event.get("markets") or []
            for m in markets:
                condition_id = m.get("conditionId") or m.get("condition_id")
                if not condition_id:
                    continue
                if condition_id in seen:
                    explain_filters["deduped"] += 1
                    continue
                market_flat = _flatten_market(event, m)
                explain_filters["total_found"] += 1
                seen[condition_id] = market_flat

    # Score by fuzzy relevance to query plus volume
    for m in seen.values():
        text = f"{m.get('question','')} {m.get('event_title','')}".lower()
        relevance = fuzz.partial_ratio(query.lower(), text)
        best_keyword_match = max(fuzz.partial_ratio(kw.lower(), text) for kw in keywords) if keywords else 0
        volume = m.get("volume_usd", 0) or 0
        score = relevance * 0.7 + min(volume, 1_000_000) / 1_000_000 * 30  # weight relevance higher, cap volume influence
        m["relevance_score"] = score
        m["relevance_match"] = relevance
        m["best_keyword_match"] = best_keyword_match
        scored.append(m)

    candidates = sorted(scored, key=lambda x: x.get("relevance_score", 0), reverse=True)

    # Filter by keyword match
    filtered = [c for c in candidates if c.get("best_keyword_match", 0) >= keyword_match_threshold]
    explain_filters["filtered_low_keyword"] = len(candidates) - len(filtered)

    working = filtered if filtered else candidates

    # Hard filter low relevance if we have many
    if len(working) > k:
        cutoff = max(40, working[min(len(working) - 1, k * 2 - 1)]["relevance_match"])
        working = [c for c in working if c["relevance_match"] >= cutoff][:k]
    else:
        working = working[:k]

    explain = {
        "keywords": keywords,
        "filters": explain_filters,
        "returned": len(working),
        "notes": [
            "relevance_score = 0.7*fuzzy(query, text) + 0.03*min(volume,1M)",
            f"best_keyword_match >= {keyword_match_threshold} filter applied",
        ],
    }
    if allow_fallback and not working:
        proxy_theses = generate_proxy_theses(query)
        explain["fallback"] = {"proxy_theses": proxy_theses}
        for proxy in proxy_theses:
            proxy_candidates, proxy_explain = discover_markets(
                proxy, k=k, keyword_match_threshold=keyword_match_threshold, allow_fallback=False
            )
            for c in proxy_candidates:
                if c["condition_id"] not in {m["condition_id"] for m in working}:
                    working.append(c)
        explain["returned"] = len(working)
    return working, explain


def _flatten_market(event: Dict[str, Any], market: Dict[str, Any]) -> Dict[str, Any]:
    volume = float(market.get("volume", market.get("volumeNum", 0)) or 0)
    clob_token_ids = market.get("clobTokenIds") or market.get("clobTokenIds".lower()) or "[]"
    try:
        import json

        token_ids = json.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
    except Exception:
        token_ids = []

    yes_token_id = token_ids[0] if token_ids else None
    no_token_id = token_ids[1] if len(token_ids) > 1 else None

    return {
        "condition_id": market.get("conditionId") or market.get("condition_id"),
        "yes_token_id": yes_token_id,
        "no_token_id": no_token_id,
        "token_id": yes_token_id,
        "question": market.get("question", ""),
        "event_title": event.get("title", ""),
        "volume_usd": volume,
        "outcome_yes_price": _parse_price(market),
        "end_date": event.get("endDate") or market.get("endDate") or market.get("closedTs"),
        "status": market.get("status", "open"),
    }


def _parse_price(market: Dict[str, Any]) -> float:
    prices = market.get("outcomePrices")
    if not prices:
        return 0.5
    try:
        if isinstance(prices, str):
            prices = prices.strip("[]").split(",")
        return float(prices[0])
    except Exception:
        return 0.5
