"""
Correlation Analysis & Signal Generation Module
================================================
Computes Pearson correlations and generates trading signals based on thresholds.
"""

from typing import Dict, List, Iterable

import pandas as pd
import numpy as np


MIN_OVERLAPPING_DAYS = 10
CORRELATION_THRESHOLD_POSITIVE = 0.65
CORRELATION_THRESHOLD_NEGATIVE = -0.65


def compute_correlation_matrix(
    belief_series: pd.Series,
    candidate_series: Dict[str, pd.Series]
) -> pd.DataFrame:
    """
    Compute Pearson correlation between belief market and all candidates.
    Uses inner join to align timestamps - only days present in BOTH series are used.

    Returns DataFrame with columns: [token_id, correlation, n_points]
    """
    results = []

    for token_id, series in candidate_series.items():
        # CRITICAL: Align time series using inner join
        # This ensures correlation is only computed on overlapping dates
        aligned = pd.concat([belief_series, series], axis=1, join='inner')

        n_points = len(aligned)

        if n_points < MIN_OVERLAPPING_DAYS:
            # Not enough overlapping data for reliable correlation
            continue

        # Extract aligned values
        belief_vals = aligned.iloc[:, 0].values
        candidate_vals = aligned.iloc[:, 1].values

        # Compute Pearson correlation coefficient
        # Using numpy for explicit control: r = cov(X,Y) / (std(X) * std(Y))
        belief_mean = np.mean(belief_vals)
        candidate_mean = np.mean(candidate_vals)

        belief_std = np.std(belief_vals, ddof=1)
        candidate_std = np.std(candidate_vals, ddof=1)

        # Handle zero variance (constant prices)
        if belief_std == 0 or candidate_std == 0:
            continue

        covariance = np.mean((belief_vals - belief_mean) * (candidate_vals - candidate_mean))
        correlation = covariance / (belief_std * candidate_std)

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
    markets_lookup: Dict[str, Dict],
    threshold_positive: float = CORRELATION_THRESHOLD_POSITIVE,
    threshold_negative: float = CORRELATION_THRESHOLD_NEGATIVE
) -> pd.DataFrame:
    """
    Generate trading signals based on correlation thresholds.

    Signal Logic:
    - r > threshold_positive: Asset moves WITH thesis -> Buy YES
    - r < threshold_negative: Asset moves AGAINST thesis -> Buy NO (short YES)
    - threshold_negative <= r <= threshold_positive: Uncorrelated noise -> Discard
    """
    signals = []

    for _, row in correlation_df.iterrows():
        r = row['correlation']
        token_id = row['token_id']
        n_points = row['n_points']

        market_info = markets_lookup.get(token_id, {})

        if r > threshold_positive:
            action = 'BUY YES'
            signal_strength = r
        elif r < threshold_negative:
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


def compute_rolling_correlations(
    belief_series: pd.Series,
    candidate_series: Dict[str, pd.Series],
    windows: Iterable[int]
) -> Dict[int, pd.DataFrame]:
    """
    Compute rolling Pearson correlations between belief and candidates.

    Returns dict keyed by window size (days), each value is a DataFrame with
    columns: [date, token_id, correlation].
    """
    results: Dict[int, List[Dict[str, object]]] = {}

    for window in windows:
        window_rows: List[Dict[str, object]] = []

        for token_id, series in candidate_series.items():
            aligned = pd.concat([belief_series, series], axis=1, join='inner')
            if len(aligned) < max(MIN_OVERLAPPING_DAYS, window):
                continue

            rolling_corr = aligned.iloc[:, 0].rolling(window=window).corr(aligned.iloc[:, 1])
            rolling_corr = rolling_corr.dropna()

            for idx, value in rolling_corr.items():
                window_rows.append({
                    'date': idx,
                    'token_id': token_id,
                    'correlation': float(np.clip(value, -1.0, 1.0))
                })

        results[window] = pd.DataFrame(window_rows)

    return results
