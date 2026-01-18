"""
Portfolio Output & Formatting Module
=====================================
Handles console output and CSV export for portfolio results.
"""

from typing import Any, Dict, Iterable
import json
from datetime import datetime, timezone

import pandas as pd

from .correlation import compute_rolling_correlations


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

    # Add belief info to output
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


def _series_to_points(series: pd.Series) -> list:
    return [
        {'date': idx.date().isoformat() if hasattr(idx, 'date') else str(idx), 'value': float(val)}
        for idx, val in series.items()
    ]


def _compute_position_pnl_series(series: pd.Series, action: str) -> pd.Series:
    if series.empty:
        return series

    if action == 'BUY NO':
        series = 1.0 - series

    entry_price = float(series.iloc[0])
    if entry_price == 0:
        return pd.Series(dtype=float)

    pnl = (series / entry_price) - 1.0
    return pnl


def generate_portfolio_timeseries(
    portfolio_df: pd.DataFrame,
    anchor: Dict,
    thesis: str,
    anchor_series: pd.Series,
    candidate_series: Dict[str, pd.Series],
    windows: Iterable[int] = (7, 14, 30)
) -> Dict[str, Any]:
    """
    Generate time-series analytics dictionary.
    Includes rolling correlations, price paths, and PnL curves.
    """
    rolling = compute_rolling_correlations(anchor_series, candidate_series, windows)

    price_series = {
        'anchor': _series_to_points(anchor_series),
        'candidates': {
            token_id: _series_to_points(series) for token_id, series in candidate_series.items()
        }
    }

    position_pnls = {}
    pnl_frames = []
    weights = {}

    # Ensure portfolio_df uses the same token_id format as candidate_series
    for _, row in portfolio_df.iterrows():
        token_id = row['token_id']
        action = row['action']
        weight = float(row['weight']) if 'weight' in row else 0.0
        weights[token_id] = weight

        series = candidate_series.get(token_id)
        if series is None or series.empty:
            continue

        pnl_series = _compute_position_pnl_series(series, action)
        if pnl_series.empty:
            continue

        position_pnls[token_id] = _series_to_points(pnl_series)
        pnl_frames.append(pnl_series.rename(token_id))

    if pnl_frames:
        pnl_df = pd.concat(pnl_frames, axis=1, join='outer').sort_index()
        pnl_df = pnl_df.ffill().fillna(0.0)
        weighted = pnl_df.mul(pd.Series(weights), axis=1)
        portfolio_pnl = weighted.sum(axis=1)
        portfolio_pnl_points = _series_to_points(portfolio_pnl)
    else:
        portfolio_pnl_points = []

    rolling_json = {
        str(window): [
            {
                'date': row['date'].date().isoformat() if hasattr(row['date'], 'date') else str(row['date']),
                'token_id': row['token_id'],
                'correlation': row['correlation']
            }
            for _, row in df.iterrows()
        ]
        for window, df in rolling.items()
    }

    return {
        'metadata': {
            'thesis': thesis,
            'anchor_token_id': anchor.get('token_id'),
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'rolling_windows_days': [int(w) for w in windows]
        },
        'price_series': price_series,
        'rolling_correlations': rolling_json,
        'pnl_curves': {
            'portfolio': portfolio_pnl_points,
            'positions': position_pnls
        }
    }


def save_portfolio_json(
    portfolio_df: pd.DataFrame,
    anchor: Dict,
    thesis: str,
    anchor_series: pd.Series,
    candidate_series: Dict[str, pd.Series],
    windows: Iterable[int] = (7, 14, 30)
) -> str:
    """
    Save time-series analytics to JSON for visualization.
    Includes rolling correlations, price paths, and PnL curves.
    """
    safe_thesis = "".join(c if c.isalnum() else "_" for c in thesis.lower())
    filename = f"quant_basket_{safe_thesis}_timeseries.json"

    payload = generate_portfolio_timeseries(
        portfolio_df, anchor, thesis, anchor_series, candidate_series, windows
    )

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

    print(f"\nSaved time-series JSON to: {filename}")
    return filename
