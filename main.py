"""
Polymarket Thematic Quant Fund Generator - Main Orchestrator
=============================================================
Uses AI-powered anchor selection and statistical correlation to build
thematic portfolios from prediction market assets.

Flow:
1. Gemini generates keywords from thesis
2. DB query filters markets using keywords
3. AI selects anchor with confidence score
4. If confidence < 90%: retry with 5 alternative ideas
5. Compute correlations and generate portfolio

Usage:
    python main.py "Lakers good season"
    python main.py "Trump loses"
    python main.py "Bitcoin above 100k"
"""

import argparse
import sys
from typing import Optional

import pandas as pd

from llm_keywords import generate_keywords
from llm_proxy import generate_proxy_theses
from search_pipeline import query_markets_by_keywords
from market_data import fetch_price_history, HISTORY_DAYS, TOP_N_LIQUID_MARKETS
from belief_selection import select_anchor_market, AnchorMarket
from correlation import compute_correlation_matrix, generate_signals, construct_portfolio, MIN_OVERLAPPING_DAYS
from portfolio_output import print_portfolio_table, save_portfolio_csv

CONFIDENCE_THRESHOLD = 0.90


def run_quant_fund(thesis: str) -> Optional[pd.DataFrame]:
    """
    Main execution pipeline for the Anchor-Beta strategy.

    Uses DB-first market discovery with confidence-based retry:
    1. Generate keywords from thesis
    2. Query DB for markets matching keywords
    3. Select anchor with confidence check
    4. If low confidence, retry with alternative ideas
    5. Compute correlations and build portfolio

    Args:
        thesis: User's abstract belief (e.g., "Lakers good season", "Trump loses")

    Returns:
        Portfolio DataFrame or None if pipeline fails
    """
    print("=" * 100)
    print("POLYMARKET THEMATIC QUANT FUND GENERATOR")
    print("Strategy: AI-Powered Anchor-Beta Correlation")
    print("=" * 100)
    print(f"\nThesis: \"{thesis}\"")
    print(f"History Window: {HISTORY_DAYS} days")
    print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD:.0%}")

    # Step 1: Generate keywords from thesis
    print(f"\n-> [STEP 1] Generating keywords from thesis...")
    keywords = generate_keywords(thesis)
    print(f"   Keywords: {keywords}")

    # Step 2: Query DB for markets
    print(f"\n-> [STEP 2] Querying database for markets...")
    markets = query_markets_by_keywords(keywords, limit=TOP_N_LIQUID_MARKETS)

    if not markets:
        print("[ERROR] No markets found in database matching keywords")
        return None

    print(f"   Found {len(markets)} markets in database")

    # Step 3: AI-powered anchor selection with confidence check
    print(f"\n-> [STEP 3] Selecting anchor market...")
    anchor = select_anchor_market(markets, thesis)

    # Step 4: Check confidence threshold
    if anchor is None or anchor.confidence < CONFIDENCE_THRESHOLD:
        confidence_str = f"{anchor.confidence:.0%}" if anchor else "N/A"
        print(f"\n-> [STEP 4] Confidence {confidence_str} < {CONFIDENCE_THRESHOLD:.0%} threshold")
        print(f"   Retrying with alternative ideas...")

        # Generate 5 alternative theses
        alt_theses = generate_proxy_theses(thesis)
        print(f"   Alternative theses: {alt_theses}")

        # Generate keywords for all alternative theses
        alt_keywords = []
        for alt in alt_theses:
            alt_kws = generate_keywords(alt)
            alt_keywords.extend(alt_kws)

        # Deduplicate keywords
        alt_keywords = list(set(alt_keywords))
        print(f"   Alternative keywords: {alt_keywords}")

        # Query DB with alternative keywords
        markets = query_markets_by_keywords(alt_keywords, limit=TOP_N_LIQUID_MARKETS)

        if markets:
            print(f"   Found {len(markets)} markets with alternative keywords")
            anchor = select_anchor_market(markets, thesis)
        else:
            anchor = None

        # Final confidence check
        if anchor is None or anchor.confidence < CONFIDENCE_THRESHOLD:
            final_conf = f"{anchor.confidence:.0%}" if anchor else "N/A"
            print(f"\n[TERMINATE] No anchor with >= {CONFIDENCE_THRESHOLD:.0%} confidence found")
            print(f"   Best confidence achieved: {final_conf}")
            print("   Consider refining your thesis or try a different topic")
            return None

    print(f"\n-> [STEP 4] Anchor confidence {anchor.confidence:.0%} >= {CONFIDENCE_THRESHOLD:.0%} ✓")

    # Build lookup dict for later
    markets_lookup = {m['yes_token_id']: m for m in markets}
    for m in markets:
        if m.get('no_token_id'):
            markets_lookup[m['no_token_id']] = m

    # Step 5: Fetch price history for anchor
    print(f"\n-> [STEP 5] Fetching {HISTORY_DAYS}-day price history for anchor...")
    anchor_series = fetch_price_history(anchor.token_id, days=HISTORY_DAYS)

    if anchor_series is None or len(anchor_series) < MIN_OVERLAPPING_DAYS:
        print(f"   [ERROR] Insufficient price history for anchor (need {MIN_OVERLAPPING_DAYS}+ days)")
        return None

    print(f"   Anchor has {len(anchor_series)} daily price points")

    # Step 6: Fetch price history for all candidates (excluding anchor)
    print(f"\n-> [STEP 6] Fetching price history for candidate markets...")
    candidate_series = {}
    fetched = 0
    failed = 0

    for i, market in enumerate(markets):
        # Skip the anchor itself (check both yes and no token)
        if market['yes_token_id'] == anchor.token_id:
            continue
        if market.get('no_token_id') == anchor.token_id:
            continue

        # Fetch price history for YES token
        series = fetch_price_history(market['yes_token_id'], days=HISTORY_DAYS)

        if series is not None and len(series) >= MIN_OVERLAPPING_DAYS:
            candidate_series[market['yes_token_id']] = series
            fetched += 1
        else:
            failed += 1

        # Progress indicator
        if (i + 1) % 20 == 0:
            print(f"   Processed {i + 1}/{len(markets)} markets...")

    print(f"   Successfully fetched history for {fetched} markets ({failed} failed/insufficient)")

    if not candidate_series:
        print("[ERROR] No valid candidate price histories")
        return None

    # Step 7: Compute correlation matrix
    print(f"\n-> [STEP 7] Computing Pearson correlations (aligned time series)...")
    correlation_df = compute_correlation_matrix(anchor_series, candidate_series)

    if correlation_df.empty:
        print("[ERROR] No valid correlations computed")
        return None

    print(f"   Computed correlations for {len(correlation_df)} markets")

    # Step 8: Generate trading signals
    print(f"\n-> [STEP 8] Generating signals...")
    signals_df = generate_signals(correlation_df, markets_lookup)

    if signals_df.empty:
        print(f"   [RESULT] No markets meet correlation threshold")
        print("   Consider trying a different thesis")
        return None

    print(f"   Found {len(signals_df)} correlated markets")

    # Step 9: Construct portfolio with weights
    portfolio_df = construct_portfolio(signals_df)

    # Step 10: Output results
    # Convert AnchorMarket to dict format for output functions
    anchor_dict = {
        'question': anchor.market['question'],
        'token_id': anchor.token_id,
        'volume_usd': anchor.market['volume_usd'],
        'token_choice': anchor.token_choice,
        'ai_reasoning': anchor.reasoning,
        'ai_confidence': anchor.confidence,
    }

    print_portfolio_table(portfolio_df, anchor_dict, thesis)
    save_portfolio_csv(portfolio_df, anchor_dict, thesis)

    return portfolio_df


def main():
    """
    Command-line entry point.
    Usage: python main.py <thesis>
    """
    parser = argparse.ArgumentParser(
        description='Polymarket Thematic Quant Fund Generator (AI-Powered)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "Lakers good season"
  python main.py "Trump loses"
  python main.py "Bitcoin above 100k"
  python main.py "Interest rates will rise"
        """
    )
    parser.add_argument(
        'thesis',
        type=str,
        help='Your thesis/belief to build a thematic basket around'
    )

    args = parser.parse_args()

    # Run the strategy
    portfolio = run_quant_fund(args.thesis)

    if portfolio is None:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
