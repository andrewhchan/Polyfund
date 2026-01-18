"""
Market Data Fetching Module
============================
Handles API calls to Polymarket for market and price history data.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential


POLY_GAMMA_API = os.getenv('POLYMARKET_GAMMA_BASE_URL', 'https://gamma-api.polymarket.com')
POLY_CLOB_API = os.getenv('POLYMARKET_CLOB_BASE_URL', 'https://clob.polymarket.com')

HISTORY_DAYS = 30
TOP_N_LIQUID_MARKETS = 100


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
                        token_ids = json.loads(clob_token_ids)
                    else:
                        token_ids = clob_token_ids
                    yes_token_id = token_ids[0] if token_ids else None
                    no_token_id = token_ids[1] if len(token_ids) > 1 else None
                except (json.JSONDecodeError, IndexError):
                    yes_token_id = None
                    no_token_id = None

                if not condition_id or not yes_token_id:
                    continue

                volume = float(market.get('volume', market.get('volumeNum', 0)))

                all_markets.append({
                    'condition_id': condition_id,
                    'yes_token_id': yes_token_id,
                    'no_token_id': no_token_id,
                    'token_id': yes_token_id,  # Keep for backward compatibility
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


def search_polymarket_events(keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Search Polymarket Gamma public search endpoint for events by keyword.
    """
    params = {'q': keyword, 'limit': limit}
    response = requests.get(f"{POLY_GAMMA_API}/public-search", params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        if 'events' in data and isinstance(data['events'], list):
            return data['events']
        if 'data' in data and isinstance(data['data'], list):
            return data['data']
        return []
    if isinstance(data, list):
        return data
    return []


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
