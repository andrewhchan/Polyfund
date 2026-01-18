"""
Portfolio Output & Formatting Module
=====================================
Handles console output and CSV export for portfolio results.
"""

from typing import Dict

import pandas as pd


def print_portfolio_table(
    portfolio_df: pd.DataFrame,
    anchor: Dict,
    thesis: str
) -> None:
    """
    Print a professional console table of the portfolio.
    """
    print("\n" + "=" * 100)
    print(f"THEMATIC QUANT FUND: '{thesis.upper()}' BASKET (AI-POWERED)")
    print("=" * 100)
    print(f"\nANCHOR ASSET (AI-Selected Numerical Proxy):")
    print(f"  {anchor['question'][:90]}")
    print(f"  Token: {anchor.get('token_choice', 'YES')} ({anchor['token_id'][:20]}...)")
    print(f"  Volume: ${anchor['volume_usd']:,.2f}")
    if 'ai_reasoning' in anchor:
        print(f"  AI Reasoning: {anchor['ai_reasoning']}")
    if 'ai_confidence' in anchor:
        print(f"  AI Confidence: {anchor['ai_confidence']:.0%}")
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
    filename = f"quant_basket_{safe_thesis}_ai.csv"

    # Add anchor info to output
    output_df = portfolio_df.copy()
    output_df['anchor_question'] = anchor['question']
    output_df['anchor_token_id'] = anchor['token_id']
    output_df['anchor_token_choice'] = anchor.get('token_choice', 'YES')
    output_df['thesis'] = thesis

    if 'ai_reasoning' in anchor:
        output_df['anchor_ai_reasoning'] = anchor['ai_reasoning']
    if 'ai_confidence' in anchor:
        output_df['anchor_ai_confidence'] = anchor['ai_confidence']

    # Reorder columns for clarity
    cols = [
        'thesis', 'correlation', 'action', 'weight_pct', 'n_data_points',
        'question', 'token_id', 'volume_usd', 'anchor_question', 'anchor_token_id',
        'anchor_token_choice', 'anchor_ai_reasoning', 'anchor_ai_confidence'
    ]
    output_df = output_df[[c for c in cols if c in output_df.columns]]

    output_df.to_csv(filename, index=False)
    print(f"\nSaved portfolio to: {filename}")

    return filename
