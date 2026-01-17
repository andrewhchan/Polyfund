"""
Portfolio Output & Formatting Module
=====================================
Handles console output and CSV export for portfolio results.
"""

from typing import Dict

import pandas as pd


def print_portfolio_table(
    portfolio_df: pd.DataFrame,
    belief: Dict,
    thesis: str
) -> None:
    """
    Print a professional console table of the portfolio.
    """
    print("\n" + "=" * 100)
    print(f"THEMATIC QUANT FUND: '{thesis.upper()}' BASKET (SEMANTIC AI-ENHANCED)")
    print("=" * 100)
    print(f"\nBELIEF MARKET (Market Proxy with Semantic Validation):")
    print(f"  {belief['question'][:90]}")
    print(f"  Token: {belief['token_id'][:20]}...  |  Volume: ${belief['volume_usd']:,.2f}")
    if 'semantic_analysis' in belief:
        print(f"  Intent Match: {belief['semantic_analysis']['reasoning']}")
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
    belief: Dict,
    thesis: str
) -> str:
    """
    Save portfolio to CSV file.
    Returns the filename.
    """
    # Sanitize thesis for filename
    safe_thesis = "".join(c if c.isalnum() else "_" for c in thesis.lower())
    filename = f"quant_basket_{safe_thesis}_semantic.csv"

    # Add belief info to output
    output_df = portfolio_df.copy()
    output_df['belief_question'] = belief['question']
    output_df['belief_token_id'] = belief['token_id']
    output_df['thesis'] = thesis
    
    if 'semantic_analysis' in belief:
        output_df['belief_semantic_alignment'] = belief['semantic_analysis']['alignment_score']
        output_df['belief_intent_match'] = belief['semantic_analysis']['reasoning']

    # Reorder columns for clarity
    cols = [
        'thesis', 'correlation', 'action', 'weight_pct', 'n_data_points',
        'question', 'token_id', 'volume_usd',
        'belief_question', 'belief_token_id', 'belief_semantic_alignment', 'belief_intent_match'
    ]
    output_df = output_df[[c for c in cols if c in output_df.columns]]

    output_df.to_csv(filename, index=False)
    print(f"\nSaved portfolio to: {filename}")

    return filename
