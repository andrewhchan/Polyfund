"""
Market Data Fetching Module
============================
Handles API calls to Polymarket for price history data.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential


POLY_CLOB_API = os.getenv('POLYMARKET_CLOB_BASE_URL', 'https://clob.polymarket.com')

HISTORY_DAYS = 30


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
