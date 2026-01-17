"""
Anchor Market Selection Module
===============================
Two-step process: broad fuzzy search + semantic filtering via MockAI.
"""

from typing import Dict, List, Optional

from rapidfuzz import fuzz, process

from mock_ai import MockAIAnchorAnalyzer


TOP_SEMANTIC_CANDIDATES = 10


def find_anchor_market_semantic(
    markets: List[Dict],
    thesis_keyword: str,
    ai_analyzer: MockAIAnchorAnalyzer
) -> Optional[Dict]:
    """
    Find the most semantically aligned market matching the thesis keyword.
    
    Two-step process:
    1. Broad Search: Use fuzzy matching to get top 10 candidates
    2. Semantic Filtering: Use MockAI to find the best intent-aligned match
    
    Returns the anchor market with the correct token_id (YES or NO) selected
    based on semantic alignment.
    """
    print(f"\n-> [STEP 1] Broad fuzzy search for '{thesis_keyword}'...")

    # Build search corpus
    search_texts = []
    for m in markets:
        combined = f"{m['question']} {m['event_title']}".lower()
        search_texts.append(combined)

    # Get top 10 fuzzy matches
    candidates = process.extract(
        thesis_keyword.lower(),
        search_texts,
        scorer=fuzz.partial_ratio,
        limit=TOP_SEMANTIC_CANDIDATES,
        score_cutoff=40  # Lower threshold to get more candidates for semantic filtering
    )

    if not candidates:
        print(f"   [ERROR] No markets found matching '{thesis_keyword}'")
        return None

    print(f"   Found {len(candidates)} fuzzy matches. Moving to semantic analysis...")

    # Step 2: Semantic filtering
    print(f"\n-> [STEP 2] Semantic intent alignment analysis...")

    best_anchor = None
    best_score = -1.0

    for matched_text, fuzzy_score, idx in candidates:
        market = markets[idx]
        
        # Run semantic analysis
        analysis = ai_analyzer.analyze_candidate(
            user_thesis=thesis_keyword,
            market_question=market['question'],
            yes_token_id=market['yes_token_id'],
            no_token_id=market.get('no_token_id')
        )

        alignment_score = analysis['alignment_score']

        # Combine fuzzy score (0-100) with semantic alignment (0-1)
        # Weight: 40% fuzzy matching, 60% semantic alignment
        combined_score = (fuzzy_score / 100.0) * 0.4 + alignment_score * 0.6

        print(f"   Candidate: {market['question'][:70]}...")
        print(f"      Fuzzy: {fuzzy_score:.0f}% | Semantic: {alignment_score:.2f} | Combined: {combined_score:.3f}")
        print(f"      Decision: {analysis['token_choice']} token | {analysis['reasoning']}")

        if combined_score > best_score:
            best_score = combined_score
            best_anchor = market.copy()
            # Override token_id with semantically-selected token
            best_anchor['token_id'] = analysis['recommended_token_id']
            best_anchor['semantic_analysis'] = analysis

    if best_anchor is None:
        print(f"   [ERROR] No anchor market selected")
        return None

    print(f"\n   ✓ ANCHOR SELECTED:")
    print(f"      Market: {best_anchor['question'][:80]}...")
    print(f"      Token: {best_anchor['semantic_analysis']['token_choice']} ({best_anchor['token_id'][:20]}...)")
    print(f"      Volume: ${best_anchor['volume_usd']:,.2f}")
    print(f"      Confidence: {best_score:.1%}")

    return best_anchor
