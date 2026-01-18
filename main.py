"""
Polymarket Thematic Quant Fund Generator - Main Orchestrator
=============================================================
Uses AI-powered anchor selection and statistical correlation to build
thematic portfolios from prediction market assets.

Usage:
    python main.py "Lakers good season"
    python main.py "Trump loses"
    python main.py "Bitcoin above 100k"
"""

import argparse
import sys
from typing import Optional

import pandas as pd

from market_data import fetch_polymarket_markets, fetch_price_history, HISTORY_DAYS, TOP_N_LIQUID_MARKETS
from anchor_selection import select_anchor_market, AnchorMarket
from correlation import compute_correlation_matrix, generate_signals, construct_portfolio, MIN_OVERLAPPING_DAYS
from portfolio_output import print_portfolio_table, save_portfolio_csv


def run_quant_fund(thesis: str) -> Optional[pd.DataFrame]:
    """
    Main execution pipeline for the Anchor-Beta strategy.

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

    # Step 1: Fetch liquid markets
    markets = fetch_polymarket_markets(limit=TOP_N_LIQUID_MARKETS)
    if not markets:
        print("[ERROR] Failed to fetch markets")
        return None

    # Build lookup dict for later
    markets_lookup = {m['yes_token_id']: m for m in markets}
    # Also add no_token_id lookups
    for m in markets:
        if m.get('no_token_id'):
            markets_lookup[m['no_token_id']] = m

    # Step 2: AI-powered anchor selection
    anchor = select_anchor_market(markets, thesis)
    if anchor is None:
        print("[ERROR] Failed to select anchor market")
        return None

    # Step 3: Fetch price history for anchor
    print(f"\n-> Fetching {HISTORY_DAYS}-day price history for anchor...")
    anchor_series = fetch_price_history(anchor.token_id, days=HISTORY_DAYS)

    if anchor_series is None or len(anchor_series) < MIN_OVERLAPPING_DAYS:
        print(f"   [ERROR] Insufficient price history for anchor (need {MIN_OVERLAPPING_DAYS}+ days)")
        return None

    print(f"   Anchor has {len(anchor_series)} daily price points")

    # Step 4: Fetch price history for all candidates (excluding anchor)
    print(f"\n-> Fetching price history for candidate markets...")
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

    # Step 5: Compute correlation matrix
    print(f"\n-> Computing Pearson correlations (aligned time series)...")
    correlation_df = compute_correlation_matrix(anchor_series, candidate_series)

    if correlation_df.empty:
        print("[ERROR] No valid correlations computed")
        return None

    print(f"   Computed correlations for {len(correlation_df)} markets")

    # Step 6: Generate trading signals
    print(f"\n-> Generating signals...")
    signals_df = generate_signals(correlation_df, markets_lookup)

    if signals_df.empty:
        print(f"   [RESULT] No markets meet correlation threshold")
        print("   Consider trying a different thesis")
        return None

    print(f"   Found {len(signals_df)} correlated markets")

    # Step 7: Construct portfolio with weights
    portfolio_df = construct_portfolio(signals_df)

    # Step 8: Output results
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
