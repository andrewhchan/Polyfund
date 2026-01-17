"""
Polymarket Thematic Quant Fund Generator - "Anchor-Beta" Strategy
==================================================================
Uses statistical correlation to bundle prediction market assets into a
thematic portfolio based on a user-provided thesis keyword.

Strategy Logic:
1. Find the most liquid market matching the thesis keyword (Anchor Asset)
2. Fetch price history for top liquid markets
3. Compute Pearson correlation between Anchor and candidates
4. Build portfolio: r > 0.65 = Buy YES, r < -0.65 = Buy NO
5. Weight by correlation strength |r|

Author: Quant Fund Generator
"""

import sys
import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

import pandas as pd
import numpy as np
import requests
from rapidfuzz import fuzz, process
from tenacity import retry, stop_after_attempt, wait_exponential

# =============================================================================
# CONFIGURATION
# =============================================================================

POLY_GAMMA_API = 'https://gamma-api.polymarket.com'
POLY_CLOB_API = 'https://clob.polymarket.com'

# Correlation thresholds for signal generation
CORRELATION_THRESHOLD_POSITIVE = 0.65   # r > 0.65: Buy YES
CORRELATION_THRESHOLD_NEGATIVE = -0.65  # r < -0.65: Buy NO

# Minimum data points required for valid correlation
MIN_OVERLAPPING_DAYS = 10

# Number of candidate markets to analyze
TOP_N_LIQUID_MARKETS = 100

# History window in days
HISTORY_DAYS = 30


# =============================================================================
# API FUNCTIONS WITH RETRY LOGIC
# =============================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_polymarket_markets(limit: int = TOP_N_LIQUID_MARKETS) -> List[Dict]:
    """
    Fetch active Polymarket markets sorted by volume (liquidity proxy).
    Returns flattened list of individual markets with their metadata.
    """
    print(f"-> Fetching top {limit} liquid Polymarket markets...")

    all_markets = []
    api_limit = 100
    offset = 0

    while len(all_markets) < limit:
        params = {
            'active': 'true',
            'closed': 'false',
            'limit': api_limit,
            'offset': offset
        }

        response = requests.get(f"{POLY_GAMMA_API}/events", params=params, timeout=15)
        response.raise_for_status()
        events = response.json()

        if not events:
            break

        for event in events:
            markets = event.get('markets', [])
            for market in markets:
                # Extract the condition_id which is used for price history
                condition_id = market.get('conditionId', '')
                clob_token_ids = market.get('clobTokenIds', '[]')

                # Parse clobTokenIds - need the YES token (first one)
                try:
                    if isinstance(clob_token_ids, str):
                        import json
                        token_ids = json.loads(clob_token_ids)
                    else:
                        token_ids = clob_token_ids
                    yes_token_id = token_ids[0] if token_ids else None
                except (json.JSONDecodeError, IndexError):
                    yes_token_id = None

                if not condition_id or not yes_token_id:
                    continue

                volume = float(market.get('volume', market.get('volumeNum', 0)))

                all_markets.append({
                    'condition_id': condition_id,
                    'token_id': yes_token_id,
                    'question': market.get('question', ''),
                    'event_title': event.get('title', ''),
                    'volume_usd': volume,
                    'outcome_yes_price': float(market.get('outcomePrices', '[0.5]').strip('[]').split(',')[0]) if market.get('outcomePrices') else 0.5
                })

        offset += api_limit
        if len(events) < api_limit:
            break

    # Sort by volume descending and take top N
    all_markets.sort(key=lambda x: x['volume_usd'], reverse=True)
    all_markets = all_markets[:limit]

    print(f"   Found {len(all_markets)} markets (sorted by volume)")
    return all_markets


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_price_history(token_id: str, days: int = HISTORY_DAYS) -> Optional[pd.Series]:
    """
    Fetch OHLC price history for a market from CLOB API.
    Returns a pandas Series with datetime index and closing prices.

    API: https://clob.polymarket.com/prices-history
    Params: market (token_id), interval (1d), fidelity (60 for hourly aggregation)
    """
    end_ts = int(datetime.now(timezone.utc).timestamp())
    start_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    params = {
        'market': token_id,
        'interval': 'max',  # Get all available data
        'fidelity': 1440,   # Daily candles (minutes per candle)
    }

    try:
        response = requests.get(
            f"{POLY_CLOB_API}/prices-history",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data or 'history' not in data:
            return None

        history = data['history']
        if not history:
            return None

        # Parse the history into a time series
        # Format: list of {"t": timestamp, "p": price}
        timestamps = []
        prices = []

        for point in history:
            ts = point.get('t')
            price = point.get('p')

            if ts is None or price is None:
                continue

            # Convert timestamp to datetime (normalize to date only for daily alignment)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()

            # Filter to last N days
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            if dt >= cutoff_date:
                timestamps.append(dt)
                prices.append(float(price))

        if not timestamps:
            return None

        # Create Series, handling duplicate dates by taking the last price
        series = pd.Series(prices, index=pd.DatetimeIndex(timestamps), name=token_id)
        series = series[~series.index.duplicated(keep='last')]
        series = series.sort_index()

        return series

    except (requests.RequestException, ValueError, KeyError) as e:
        return None


# =============================================================================
# ANCHOR IDENTIFICATION
# =============================================================================

def find_anchor_market(markets: List[Dict], thesis_keyword: str) -> Optional[Dict]:
    """
    Find the most liquid market matching the thesis keyword using fuzzy matching.
    Markets are already sorted by volume, so first match is most liquid.
    """
    print(f"\n-> Searching for anchor market matching '{thesis_keyword}'...")

    # Build search corpus: combine question and event title for better matching
    search_texts = []
    for m in markets:
        combined = f"{m['question']} {m['event_title']}".lower()
        search_texts.append(combined)

    # Find best match using rapidfuzz
    result = process.extractOne(
        thesis_keyword.lower(),
        search_texts,
        scorer=fuzz.partial_ratio,
        score_cutoff=50  # Minimum match quality
    )

    if result is None:
        print(f"   [ERROR] No market found matching '{thesis_keyword}'")
        return None

    matched_text, score, idx = result
    anchor = markets[idx]

    print(f"   Anchor found (score={score}):")
    print(f"   -> {anchor['question'][:80]}...")
    print(f"   -> Volume: ${anchor['volume_usd']:,.2f}")

    return anchor


# =============================================================================
# CORRELATION ANALYSIS
# =============================================================================

def compute_correlation_matrix(
    anchor_series: pd.Series,
    candidate_series: Dict[str, pd.Series]
) -> pd.DataFrame:
    """
    Compute Pearson correlation between anchor and all candidates.
    Uses inner join to align timestamps - only days present in BOTH series are used.

    Returns DataFrame with columns: [token_id, question, correlation, n_points]
    """
    results = []

    for token_id, series in candidate_series.items():
        # CRITICAL: Align time series using inner join
        # This ensures correlation is only computed on overlapping dates
        aligned = pd.concat([anchor_series, series], axis=1, join='inner')

        n_points = len(aligned)

        if n_points < MIN_OVERLAPPING_DAYS:
            # Not enough overlapping data for reliable correlation
            continue

        # Extract aligned values
        anchor_vals = aligned.iloc[:, 0].values
        candidate_vals = aligned.iloc[:, 1].values

        # Compute Pearson correlation coefficient
        # Using numpy for explicit control: r = cov(X,Y) / (std(X) * std(Y))
        anchor_mean = np.mean(anchor_vals)
        candidate_mean = np.mean(candidate_vals)

        anchor_std = np.std(anchor_vals, ddof=1)
        candidate_std = np.std(candidate_vals, ddof=1)

        # Handle zero variance (constant prices)
        if anchor_std == 0 or candidate_std == 0:
            continue

        covariance = np.mean((anchor_vals - anchor_mean) * (candidate_vals - candidate_mean))
        correlation = covariance / (anchor_std * candidate_std)

        # Validate correlation is in valid range
        correlation = np.clip(correlation, -1.0, 1.0)

        results.append({
            'token_id': token_id,
            'correlation': correlation,
            'n_points': n_points
        })

    return pd.DataFrame(results)


def generate_signals(
    correlation_df: pd.DataFrame,
    markets_lookup: Dict[str, Dict]
) -> pd.DataFrame:
    """
    Generate trading signals based on correlation thresholds.

    Signal Logic:
    - r > 0.65: Asset moves WITH thesis -> Buy YES
    - r < -0.65: Asset moves AGAINST thesis -> Buy NO (short YES)
    - -0.65 <= r <= 0.65: Uncorrelated noise -> Discard
    """
    signals = []

    for _, row in correlation_df.iterrows():
        r = row['correlation']
        token_id = row['token_id']
        n_points = row['n_points']

        market_info = markets_lookup.get(token_id, {})

        if r > CORRELATION_THRESHOLD_POSITIVE:
            action = 'BUY YES'
            signal_strength = r
        elif r < CORRELATION_THRESHOLD_NEGATIVE:
            action = 'BUY NO'
            signal_strength = abs(r)
        else:
            # Uncorrelated - skip
            continue

        signals.append({
            'token_id': token_id,
            'question': market_info.get('question', 'Unknown'),
            'correlation': r,
            'action': action,
            'signal_strength': signal_strength,
            'n_data_points': n_points,
            'volume_usd': market_info.get('volume_usd', 0)
        })

    return pd.DataFrame(signals)


# =============================================================================
# PORTFOLIO CONSTRUCTION
# =============================================================================

def construct_portfolio(signals_df: pd.DataFrame) -> pd.DataFrame:
    """
    Construct a weighted portfolio from correlated assets.
    Weight = |r| / sum(|r|) for all selected assets.

    This creates a correlation-weighted basket where stronger
    correlations get larger allocations.
    """
    if signals_df.empty:
        return signals_df

    # Calculate weights based on correlation strength
    total_strength = signals_df['signal_strength'].sum()

    if total_strength == 0:
        return signals_df

    signals_df = signals_df.copy()
    signals_df['weight'] = signals_df['signal_strength'] / total_strength
    signals_df['weight_pct'] = signals_df['weight'] * 100

    # Sort by weight descending
    signals_df = signals_df.sort_values('weight', ascending=False)

    return signals_df


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def print_portfolio_table(
    portfolio_df: pd.DataFrame,
    anchor: Dict,
    thesis: str
) -> None:
    """
    Print a professional console table of the portfolio.
    """
    print("\n" + "=" * 100)
    print(f"THEMATIC QUANT FUND: '{thesis.upper()}' BASKET")
    print("=" * 100)
    print(f"\nANCHOR ASSET (Market Proxy):")
    print(f"  {anchor['question'][:90]}")
    print(f"  Token: {anchor['token_id'][:20]}...  |  Volume: ${anchor['volume_usd']:,.2f}")
    print("\n" + "-" * 100)
    print(f"{'CORR':>8}  {'ACTION':^10}  {'WEIGHT':>8}  {'N':>4}  {'MARKET QUESTION':<60}")
    print("-" * 100)

    for _, row in portfolio_df.iterrows():
        corr_str = f"{row['correlation']:+.3f}"
        action_str = row['action']
        weight_str = f"{row['weight_pct']:.1f}%"
        n_str = str(row['n_data_points'])
        question = row['question'][:58] + '..' if len(row['question']) > 60 else row['question']

        print(f"{corr_str:>8}  {action_str:^10}  {weight_str:>8}  {n_str:>4}  {question:<60}")

    print("-" * 100)
    print(f"\nPORTFOLIO SUMMARY:")
    print(f"  Total Assets: {len(portfolio_df)}")
    print(f"  Avg Correlation: {portfolio_df['correlation'].abs().mean():.3f}")

    buy_yes = len(portfolio_df[portfolio_df['action'] == 'BUY YES'])
    buy_no = len(portfolio_df[portfolio_df['action'] == 'BUY NO'])
    print(f"  Long Thesis (BUY YES): {buy_yes}")
    print(f"  Short Thesis (BUY NO): {buy_no}")
    print("=" * 100)


def save_portfolio_csv(
    portfolio_df: pd.DataFrame,
    anchor: Dict,
    thesis: str
) -> str:
    """
    Save portfolio to CSV file.
    Returns the filename.
    """
    # Sanitize thesis for filename
    safe_thesis = "".join(c if c.isalnum() else "_" for c in thesis.lower())
    filename = f"quant_basket_{safe_thesis}.csv"

    # Add anchor info to output
    output_df = portfolio_df.copy()
    output_df['anchor_question'] = anchor['question']
    output_df['anchor_token_id'] = anchor['token_id']
    output_df['thesis'] = thesis

    # Reorder columns for clarity
    cols = [
        'thesis', 'correlation', 'action', 'weight_pct', 'n_data_points',
        'question', 'token_id', 'volume_usd', 'anchor_question', 'anchor_token_id'
    ]
    output_df = output_df[[c for c in cols if c in output_df.columns]]

    output_df.to_csv(filename, index=False)
    print(f"\nSaved portfolio to: {filename}")

    return filename


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_quant_fund(thesis_keyword: str) -> Optional[pd.DataFrame]:
    """
    Main execution pipeline for the Anchor-Beta strategy.
    """
    print("=" * 100)
    print("POLYMARKET THEMATIC QUANT FUND GENERATOR")
    print("Strategy: Anchor-Beta Correlation")
    print("=" * 100)
    print(f"\nThesis Keyword: '{thesis_keyword}'")
    print(f"Correlation Thresholds: r > {CORRELATION_THRESHOLD_POSITIVE} (BUY YES) | r < {CORRELATION_THRESHOLD_NEGATIVE} (BUY NO)")
    print(f"History Window: {HISTORY_DAYS} days")

    # Step 1: Fetch liquid markets
    markets = fetch_polymarket_markets(limit=TOP_N_LIQUID_MARKETS)
    if not markets:
        print("[ERROR] Failed to fetch markets")
        return None

    # Build lookup dict for later
    markets_lookup = {m['token_id']: m for m in markets}

    # Step 2: Find anchor market
    anchor = find_anchor_market(markets, thesis_keyword)
    if not anchor:
        return None

    # Step 3: Fetch price history for anchor
    print(f"\n-> Fetching {HISTORY_DAYS}-day price history for anchor...")
    anchor_series = fetch_price_history(anchor['token_id'], days=HISTORY_DAYS)

    if anchor_series is None or len(anchor_series) < MIN_OVERLAPPING_DAYS:
        print(f"   [ERROR] Insufficient price history for anchor (need {MIN_OVERLAPPING_DAYS}+ days)")
        return None

    print(f"   Anchor has {len(anchor_series)} daily price points")

    # Step 4: Fetch price history for all candidates
    print(f"\n-> Fetching price history for {len(markets)} candidate markets...")
    candidate_series = {}
    fetched = 0
    failed = 0

    for i, market in enumerate(markets):
        # Skip the anchor itself
        if market['token_id'] == anchor['token_id']:
            continue

        series = fetch_price_history(market['token_id'], days=HISTORY_DAYS)

        if series is not None and len(series) >= MIN_OVERLAPPING_DAYS:
            candidate_series[market['token_id']] = series
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
    print(f"\n-> Generating signals (|r| > {abs(CORRELATION_THRESHOLD_NEGATIVE)})...")
    signals_df = generate_signals(correlation_df, markets_lookup)

    if signals_df.empty:
        print(f"   [RESULT] No markets meet correlation threshold |r| > {abs(CORRELATION_THRESHOLD_NEGATIVE)}")
        print("   Consider lowering threshold or trying a different thesis keyword")
        return None

    print(f"   Found {len(signals_df)} correlated markets")

    # Step 7: Construct portfolio with weights
    portfolio_df = construct_portfolio(signals_df)

    # Step 8: Output results
    print_portfolio_table(portfolio_df, anchor, thesis_keyword)
    save_portfolio_csv(portfolio_df, anchor, thesis_keyword)

    return portfolio_df


def main():
    """
    Command-line entry point.
    Usage: python poly_quant_fund.py <thesis_keyword>
    """
    parser = argparse.ArgumentParser(
        description='Polymarket Thematic Quant Fund Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python poly_quant_fund.py Trump
  python poly_quant_fund.py Bitcoin
  python poly_quant_fund.py "Interest Rate"
  python poly_quant_fund.py Recession
        """
    )
    parser.add_argument(
        'thesis',
        type=str,
        help='Thesis keyword to build thematic basket (e.g., "Trump", "Bitcoin", "Recession")'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.65,
        help='Correlation threshold for signal generation (default: 0.65)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days of price history to analyze (default: 30)'
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=100,
        help='Number of top liquid markets to analyze (default: 100)'
    )

    args = parser.parse_args()

    # Update global config if arguments provided
    global CORRELATION_THRESHOLD_POSITIVE, CORRELATION_THRESHOLD_NEGATIVE
    global HISTORY_DAYS, TOP_N_LIQUID_MARKETS

    CORRELATION_THRESHOLD_POSITIVE = args.threshold
    CORRELATION_THRESHOLD_NEGATIVE = -args.threshold
    HISTORY_DAYS = args.days
    TOP_N_LIQUID_MARKETS = args.top_n

    # Run the strategy
    portfolio = run_quant_fund(args.thesis)

    if portfolio is None:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
