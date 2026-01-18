"""
Market Data Fetching Module
============================
Handles API calls to Polymarket for price history data.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential


POLY_CLOB_API = os.getenv('POLYMARKET_CLOB_BASE_URL', 'https://clob.polymarket.com')

HISTORY_DAYS = 30
MAX_WORKERS = 16  # Parallel concurrent requests


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
        'interval': 'max',
        'fidelity': 1440,
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

        timestamps = []
        prices = []

        for point in history:
            ts = point.get('t')
            price = point.get('p')

            if ts is None or price is None:
                continue

            dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            if dt >= cutoff_date:
                timestamps.append(dt)
                prices.append(float(price))

        if not timestamps:
            return None

        series = pd.Series(prices, index=pd.DatetimeIndex(timestamps), name=token_id)
        series = series[~series.index.duplicated(keep='last')]
        series = series.sort_index()

        return series

    except (requests.RequestException, ValueError, KeyError):
        return None


def fetch_price_history_batch(
    token_ids: List[str],
    days: int = HISTORY_DAYS,
    max_workers: int = MAX_WORKERS,
    progress_callback=None
) -> Dict[str, Optional[pd.Series]]:
    """
    Fetch price history for multiple tokens in parallel.
    
    Args:
        token_ids: List of token IDs to fetch
        days: Number of days of history
        max_workers: Number of concurrent threads (default 16)
        progress_callback: Optional callback(completed, total) for progress tracking
    
    Returns:
        Dict mapping token_id -> pd.Series (or None if failed)
    """
    results = {}
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_token = {
            executor.submit(fetch_price_history, token_id, days): token_id
            for token_id in token_ids
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_token):
            token_id = future_to_token[future]
            try:
                series = future.result()
                results[token_id] = series
            except Exception:
                results[token_id] = None
            
            completed += 1
            if progress_callback:
                progress_callback(completed, len(token_ids))
    
    return results
