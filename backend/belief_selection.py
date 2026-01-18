"""
Anchor Market Selection Module (AI-Powered)
============================================
Uses AI to identify the best numerical proxy market for a user's abstract thesis.

Hybrid approach: Fuzzy filter first to find relevant markets, then AI picks best anchor.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from rapidfuzz import fuzz, process

from .ai_client import AIClient, AnchorSelectionResult, AIClientError


FUZZY_CANDIDATES_LIMIT = 50  # Max markets to send to AI after fuzzy filter
FUZZY_SCORE_CUTOFF = 30      # Minimum fuzzy match score (lower = more inclusive)


@dataclass
class AnchorMarket:
    """Selected anchor market with token choice."""
    market: Dict  # Full market data
    token_id: str  # Selected token (YES or NO)
    token_choice: str  # "YES" or "NO"
    reasoning: str
    confidence: float


def _fuzzy_filter_markets(
    markets: List[Dict],
    user_thesis: str
) -> List[Dict]:
    """
    Use fuzzy matching to filter markets relevant to the user's thesis.

    Args:
        markets: Full list of available markets
        user_thesis: User's abstract belief/thesis

    Returns:
        Filtered list of markets (max FUZZY_CANDIDATES_LIMIT)
    """
    if len(markets) <= FUZZY_CANDIDATES_LIMIT:
        return markets

    # Create search text for each market (question + event title)
    search_texts = [
        f"{m.get('question', '')} {m.get('event_title', '')}".lower()
        for m in markets
    ]

    # Find fuzzy matches
    matches = process.extract(
        user_thesis.lower(),
        search_texts,
        scorer=fuzz.partial_ratio,
        limit=FUZZY_CANDIDATES_LIMIT,
        score_cutoff=FUZZY_SCORE_CUTOFF
    )

    if not matches:
        # If no matches above cutoff, return top markets by volume as fallback
        print(f"   [FUZZY] No matches above score cutoff, using top {FUZZY_CANDIDATES_LIMIT} by volume")
        return markets[:FUZZY_CANDIDATES_LIMIT]

    # Get matched markets (matches returns tuples of (match_text, score, index))
    filtered_markets = [markets[idx] for _, _, idx in matches]

    return filtered_markets


def select_anchor_market(
    markets: List[Dict],
    user_thesis: str,
    ai_client: Optional[AIClient] = None
) -> Optional[AnchorMarket]:
    """
    Select the best anchor market using hybrid fuzzy + AI approach.

    Flow:
    1. Fuzzy filter: Reduce large market pool to ~50 relevant candidates
    2. AI selection: Send filtered candidates to AI for semantic analysis

    Args:
        markets: List of all available markets (should include question,
                 yes_token_id, no_token_id, volume_usd)
        user_thesis: User's abstract belief/thesis (e.g., "Lakers good season")
        ai_client: AIClient instance (creates default if None)

    Returns:
        AnchorMarket with selected market and token choice, or None if selection fails
    """
    if not markets:
        print("[ERROR] No markets provided for anchor selection")
        return None

    print(f"\n-> [AI ANCHOR SELECTION] Analyzing markets...")
    print(f"   Thesis: \"{user_thesis}\"")
    print(f"   Total markets pool: {len(markets)}")

    # Step 1: Fuzzy filter to find relevant markets
    filtered_markets = _fuzzy_filter_markets(markets, user_thesis)
    print(f"   [FUZZY] Filtered to {len(filtered_markets)} candidate markets")

    # Create AI client if not provided
    if ai_client is None:
        try:
            ai_client = AIClient()
        except AIClientError as e:
            print(f"   [ERROR] Failed to initialize AI client: {e}")
            return None

    # Step 2: Call AI to select anchor from filtered candidates
    try:
        result: AnchorSelectionResult = ai_client.select_anchor(user_thesis, filtered_markets)
    except AIClientError as e:
        print(f"   [ERROR] AI selection failed: {e}")
        return None

    # If AI returned null index, it means no suitable anchor found
    if result.market_index is None:
        print(f"   [AI] No suitable anchor found. Reasoning: {result.reasoning}")
        return None

    # Build anchor market from result
    selected_market = filtered_markets[result.market_index]
    anchor = _build_anchor_from_result(result, selected_market)

    print(f"\n   [AI SELECTED ANCHOR]")
    print(f"   Market: {selected_market['question'][:80]}...")
    print(f"   Token: {anchor.token_choice}")
    print(f"   Confidence: {anchor.confidence:.0%}")
    print(f"   Reasoning: {anchor.reasoning}")

    return anchor


def _build_anchor_from_result(
    result: AnchorSelectionResult,
    market: Dict
) -> AnchorMarket:
    """
    Convert AI result into AnchorMarket object with correct token_id.
    """
    # Get the correct token ID based on YES/NO choice
    if result.token_choice == "YES":
        token_id = market.get("yes_token_id") or market.get("token_id")
    else:
        token_id = market.get("no_token_id") or market.get("yes_token_id") or market.get("token_id")

    if not token_id:
        raise ValueError(f"No token_id found in market: {market.get('question', 'unknown')}")

    return AnchorMarket(
        market=market,
        token_id=token_id,
        token_choice=result.token_choice,
        reasoning=result.reasoning,
        confidence=result.confidence
    )


def select_arbitrary_bets(
    markets: List[Dict],
    user_thesis: str,
    k: int = 5,
    ai_client: Optional[AIClient] = None
) -> List[Dict]:
    """
    Select arbitrary bets (top k) when no single anchor is strong enough.

    Args:
        markets: List of available markets.
        user_thesis: User's abstract belief.
        k: Number of bets to select.
        ai_client: Optional AIClient instance.

    Returns:
        List of dicts formatted like portfolio items (but with simulated data).
    """
    if not markets:
        return []

    print(f"\n-> [FALLBACK] Selecting arbitrary bets (confidence < threshold)...")

    # Step 1: Fuzzy filter to find relevant markets (reuse existing logic)
    filtered_markets = _fuzzy_filter_markets(markets, user_thesis)
    
    # Create AI client if not provided
    if ai_client is None:
        try:
            ai_client = AIClient()
        except AIClientError as e:
            print(f"   [ERROR] Failed to initialize AI client: {e}")
            return []

    # Step 2: Call AI to select top bets
    selected_bets = ai_client.select_top_bets(user_thesis, filtered_markets, top_k=k)
    
    # [FALLBACK] If AI returns nothing (common for "nonsense" theses), pick top volume markets
    if not selected_bets:
        print(f"   [FALLBACK] AI selected 0 bets. Defaulting to top {k} liquid markets.")
        # Sort by volume descending
        top_vol = sorted(filtered_markets, key=lambda x: x.get("volume_usd", 0) or 0, reverse=True)[:k]
        for m in top_vol:
            selected_bets.append({
                "market": m,
                "reasoning": "High liquidity market selected as fallback.",
                "token_choice": "YES",  # Default
                "confidence": 0.1
            })

    portfolio_items = []
    for bet in selected_bets:
        m = bet["market"]
        token_choice = bet["token_choice"]
        
        # Ensure slug is available
        slug = m.get("slug")
        if not slug and "event" in m:
            slug = m["event"].get("slug")
        
        # Determine token ID
        if token_choice == "YES":
            token_id = m.get("yes_token_id") or m.get("token_id")
        else:
            token_id = m.get("no_token_id") or m.get("yes_token_id") or m.get("token_id")
            
        action = f"BUY {token_choice}"
        
        portfolio_items.append({
            "question": m.get("question"),
            "slug": slug,
            "token_id": token_id,
            "volume_usd": m.get("volume_usd"),
            "action": action,
            "weight_pct": 0,    # Placeholder
            "correlation": 0,   # Placeholder
            "n_data_points": 0, # Placeholder
            "ai_reasoning": bet.get("reasoning"),
            "ai_confidence": bet.get("confidence")
        })
        
    print(f"   [FALLBACK] Selected {len(portfolio_items)} bets.")
    return portfolio_items
