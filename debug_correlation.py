
import sys
import os
import pandas as pd
from backend.search_pipeline import discover_markets
from backend.market_data import fetch_price_history
from backend.correlation import compute_correlation_matrix
from backend.belief_selection import select_anchor_market

# Setup env
from dotenv import load_dotenv
load_dotenv()

def debug_correlation(thesis="Trump 2024"):
    print(f"--- Debugging Thesis: {thesis} ---")
    
    # 1. Discover
    print("Discovering markets...")
    markets, _ = discover_markets(thesis, k=10)
    if not markets:
        print("No markets found.")
        return

    # 2. Anchor
    print("Selecting anchor...")
    anchor = select_anchor_market(markets, thesis)
    if not anchor:
        print("No anchor selected.")
        return
    
    print(f"Anchor: {anchor.market['question']} (Token: {anchor.token_id}) Choice: {anchor.token_choice}")
    
    # 3. Fetch History
    print(f"Fetching history for anchor {anchor.token_id}...")
    anchor_series = fetch_price_history(anchor.token_id, days=30)
    if anchor_series is None or len(anchor_series) == 0:
        print("No history for anchor.")
        return
    print(f"Anchor history: {len(anchor_series)} points")
    print(anchor_series)
    print("Anchor Std Dev:", anchor_series.std())

    # 4. Fetch Candidate History
    candidate_series = {}
    print("Fetching candidates...")
    for m in markets[:5]:
        yes_id = m.get("yes_token_id")
        if yes_id == anchor.token_id: continue
        
        print(f"Fetching {m['question']} (YES: {yes_id})...")
        s = fetch_price_history(yes_id, days=30)
        if s is not None:
            candidate_series[yes_id] = s
            print(f"  Got {len(s)} points")
        else:
            print("  Failed or empty")

    # 5. Correlation
    print("Computing correlations...")
    corr_df = compute_correlation_matrix(anchor_series, candidate_series)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(corr_df)


if __name__ == "__main__":
    debug_correlation(thesis="Bitcoin")
