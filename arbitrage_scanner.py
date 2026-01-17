"""
Polymarket/Opinion.Trade Arbitrage Scanner MVP - Fixed & Updated (Dec 15, 2025)
- Fetches many markets (binary + multi-outcome) using proxy URL
- True ROI for binary (hedged buys only)
- Multi-outcome arb (buy/sell spread)
- **FIXED: Multi-outcome fuzzy outcome matching**
- Clean formatted output
"""

import os
import time
import re
import json
from datetime import datetime, timezone
from itertools import combinations
from typing import List, Dict, Optional, Tuple

import requests
import pandas as pd
from rapidfuzz import fuzz, process
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

load_dotenv()

OPINION_API_KEY = os.getenv('OPINION_API_KEY')
OPINION_BASE_URL = 'https://proxy.opinion.trade:8443/openapi'  # Working proxy from docs
POLY_GAMMA_API = 'https://gamma-api.polymarket.com'
POLY_CLOB_API = 'https://clob.polymarket.com'

# Minimum ROI (in %) to report an arbitrage opportunity
ARB_THRESHOLD_PCT = 1.0
FUZZY_MATCH_THRESHOLD = 85
OPINION_RATE_LIMIT_DELAY = 0.07
MAX_DEPTH_USDC = 1000

# Fee configuration
# Polymarket: 0% fees
# Opinion.Trade: 0-2% taker fees, formula: topic_rate * price * (1-price), min $0.50
POLYMARKET_FEE_PCT = 0.0
OPINION_BASE_TOPIC_RATE = 0.08  # Assume 8% base topic rate (conservative estimate)
OPINION_MIN_FEE_USD = 0.50


def calculate_opinion_fee(price: float, notional: float) -> float:
    """
    Calculate Opinion.Trade fee for a trade.
    Fee = max(notional * topic_rate * price * (1-price), $0.50)
    Returns fee as a fraction of notional (for ROI calculation).
    """
    if notional <= 0:
        return 0.0
    effective_rate = OPINION_BASE_TOPIC_RATE * price * (1 - price)
    fee_usd = max(notional * effective_rate, OPINION_MIN_FEE_USD)
    return fee_usd / notional if notional > 0 else 0.0


def normalize_title(title: str) -> str:
    if not title:
        return ""
    normalized = title.strip()
    normalized = normalized.replace('–', '-').replace('—', '-').replace('\u00A0', ' ')
    normalized = re.sub(r'[|•·]', ' ', normalized)
    normalized = re.sub(r'\bbtc\b', 'BTC', normalized, flags=re.I)
    normalized = re.sub(r'\beth\b', 'ETH', normalized, flags=re.I)
    normalized = re.sub(r'\busd\b', 'USD', normalized, flags=re.I)
    normalized = re.sub(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}\b', '', normalized, flags=re.I)
    normalized = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
    return normalized

def normalize_price(price: float) -> float:
    """Normalize price if API returns cents (0-100)."""
    return price / 100.0 if price > 1.0 else price


def are_outcomes_mutually_exclusive(outcome_names: List[str]) -> Tuple[bool, str]:
    """
    Check if outcomes are mutually exclusive (exactly one can be true).
    Returns (is_exclusive, reason).

    Non-exclusive patterns (FALSE POSITIVES to avoid):
    - Time-based: "by March", "by June", or just dates like "March 31, 2026"
    - Threshold cumulative: "above $50k", "$200M", "$400M" - if hits higher, all lower pay
    - Before/by dates: "before Q1", "before Q2" - cumulative

    Exclusive patterns (VALID for surebet):
    - Range-based: "$50k-$60k", "$60k-$70k" - non-overlapping
    - Discrete choices: "Team A wins", "Team B wins" - exactly one winner
    """
    if len(outcome_names) < 2:
        return False, "need at least 2 outcomes"

    # Check if ALL outcomes are just dates (e.g., "March 31, 2026", "June 30, 2026")
    # This indicates nested time windows - cumulative, not exclusive
    date_pattern = r'^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}$'
    date_only_count = sum(1 for name in outcome_names if re.match(date_pattern, name.strip(), re.I))
    if date_only_count == len(outcome_names):
        return False, "all outcomes are dates (likely nested time windows)"

    # Check if ALL outcomes are just monetary values (e.g., "$200M", "$400M")
    # This indicates cumulative thresholds
    money_pattern = r'^\$[\d,.]+[kmb]?$'
    money_only_count = sum(1 for name in outcome_names if re.match(money_pattern, name.strip(), re.I))
    if money_only_count == len(outcome_names):
        return False, "all outcomes are monetary thresholds (likely cumulative)"

    # Check if ALL outcomes are just numbers/percentages
    number_pattern = r'^[\d,.]+%?$'
    number_only_count = sum(1 for name in outcome_names if re.match(number_pattern, name.strip()))
    if number_only_count == len(outcome_names):
        return False, "all outcomes are numeric thresholds (likely cumulative)"

    # Patterns that indicate NON-exclusive (nested/cumulative) outcomes
    time_patterns = [
        r'\b(?:by|before|until)\b',  # "by March", "before June"
        r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d',  # dates
        r'\bq[1-4]\b',  # quarters
        r'\b20\d{2}\b',  # years
    ]

    threshold_patterns = [
        r'\b(?:above|over|more than|greater than|>\s*\$?[\d,]+)',  # cumulative upper
        r'\b(?:below|under|less than|<\s*\$?[\d,]+)',  # cumulative lower
        r'\b(?:at least|minimum)\b',
    ]

    # Check if outcomes follow a nested time pattern
    time_matches = []
    for name in outcome_names:
        name_lower = name.lower()
        for pattern in time_patterns:
            if re.search(pattern, name_lower, re.I):
                time_matches.append(name)
                break

    # If most outcomes have time-based language, likely nested windows
    if len(time_matches) >= len(outcome_names) * 0.5:
        # Further check: are these cumulative dates?
        # Look for "by [date]" pattern which indicates cumulative
        by_pattern_count = sum(1 for name in outcome_names if re.search(r'\b(?:by|before)\b', name.lower()))
        if by_pattern_count >= 2:
            return False, f"nested time windows detected ({by_pattern_count} outcomes with 'by/before' dates)"
        # Even without "by", if all are dates, it's cumulative
        if len(time_matches) == len(outcome_names):
            return False, "all outcomes contain dates (likely nested time windows)"

    # Check for cumulative threshold patterns
    threshold_matches = []
    for name in outcome_names:
        name_lower = name.lower()
        for pattern in threshold_patterns:
            if re.search(pattern, name_lower, re.I):
                threshold_matches.append(name)
                break

    if len(threshold_matches) >= len(outcome_names) * 0.5:
        return False, f"cumulative thresholds detected ({len(threshold_matches)} outcomes with 'above/below' patterns)"

    # Check if outcome names are too similar (likely same event at different times/thresholds)
    # by checking if they share a long common prefix
    if len(outcome_names) >= 2:
        # Get all pairs and check similarity
        high_similarity_count = 0
        for name1, name2 in combinations(outcome_names, 2):
            # Remove numbers, dates, and currency for comparison
            clean1 = re.sub(r'[\d,.$%kmb]+', '', name1.lower()).strip()
            clean2 = re.sub(r'[\d,.$%kmb]+', '', name2.lower()).strip()
            # If the non-numeric parts are very similar, might be thresholds
            if clean1 == clean2 == '':
                # Both are purely numeric - definitely thresholds
                high_similarity_count += 1
            elif clean1 and clean2:
                similarity = fuzz.ratio(clean1, clean2)
                if similarity > 85:
                    high_similarity_count += 1

        # If most pairs are highly similar (just differ by numbers), likely thresholds
        total_pairs = len(outcome_names) * (len(outcome_names) - 1) / 2
        if total_pairs > 0 and high_similarity_count / total_pairs > 0.5:
            return False, "outcomes differ only by numbers (likely thresholds/dates)"

    # Passed all checks - likely mutually exclusive
    return True, "outcomes appear mutually exclusive"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_opinion_markets() -> List[Dict]:
    print("-> Fetching Opinion.Trade markets...")
    if not OPINION_API_KEY:
        print("  [ERROR] OPINION_API_KEY missing")
        return []

    all_markets = []
    headers = {"apikey": OPINION_API_KEY}

    for market_type in [0, 1]:  # 0 = binary, 1 = categorical
        page = 1
        limit = 20
        while True:
            params = {"page": page, "limit": limit, "marketType": market_type}
            try:
                time.sleep(OPINION_RATE_LIMIT_DELAY)
                response = requests.get(f"{OPINION_BASE_URL}/market", headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                if data.get('errno', -1) != 0:
                    break

                markets = data.get('result', {}).get('list', [])
                if not markets:
                    break

                for m in markets:
                    title = m.get('marketTitle', '')
                    mid = m.get('marketId', '')
                    if market_type == 0:
                        yes = m.get('yesTokenId', '').strip()
                        no = m.get('noTokenId', '').strip()
                        if yes and no:
                            all_markets.append({
                                'type': 'binary',
                                'event_id': mid,
                                'title': title,
                                'normalized_title': normalize_title(title),
                                'outcomes': {'Yes': yes, 'No': no},
                                'volume_usd': float(m.get('volume', 0)),
                                'deadline': m.get('cutoffAt')
                            })
                    elif market_type == 1:
                        children = m.get('childMarkets', [])
                        outcomes = {}
                        vol = 0
                        for c in children:
                            c_title = c.get('marketTitle', '')
                            yes = c.get('yesTokenId', '').strip()
                            if yes and c_title:
                                outcomes[c_title] = yes
                                vol += float(c.get('volume', 0))
                        if len(outcomes) >= 2:
                            all_markets.append({
                                'type': 'multi-outcome',
                                'event_id': mid,
                                'title': title,
                                'normalized_title': normalize_title(title),
                                'outcomes': outcomes,
                                'volume_usd': vol,
                                'deadline': m.get('cutoffAt')
                            })

                page += 1
            except Exception as e:
                print(f"  [ERROR] {e}")
                break

    binary = sum(1 for m in all_markets if m['type'] == 'binary')
    multi = len(all_markets) - binary
    print(f"  -> Found {len(all_markets)} markets ({binary} binary, {multi} multi-outcome)")
    return all_markets


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_polymarket_events() -> List[Dict]:
    print("-> Fetching active Polymarket events...")
    all_events = []
    limit = 1000
    offset = 0
    while True:
        params = {'active': 'true', 'closed': 'false', 'limit': limit, 'offset': offset}
        try:
            response = requests.get(f"{POLY_GAMMA_API}/events", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            for event in data:
                markets = event.get('markets', [])
                if not markets:
                    continue
                outcomes = {}
                total_vol = 0
                
                # For multi-outcome events, each market represents a different outcome
                # Use market question as outcome name, and Yes token as the outcome token
                for market in markets:
                    # Parse clobTokenIds and outcomes (both are JSON strings)
                    clob_token_ids_str = market.get('clobTokenIds', '[]')
                    outcomes_str = market.get('outcomes', '[]')
                    
                    try:
                        clob_token_ids = json.loads(clob_token_ids_str) if isinstance(clob_token_ids_str, str) else clob_token_ids_str
                        outcomes_list = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
                        
                        # For events with multiple markets, each market is a separate outcome
                        # Use the market's question as the outcome identifier and the Yes token as its price
                        if len(markets) > 1:
                            market_question = market.get('question', '').strip()
                            if market_question and len(clob_token_ids) > 0:
                                outcomes[market_question] = clob_token_ids[0]
                        else:
                            # Single market event: use standard Yes/No outcomes
                            for i, outcome in enumerate(outcomes_list):
                                if i < len(clob_token_ids) and outcome:
                                    outcomes[outcome] = clob_token_ids[i]
                    except (json.JSONDecodeError, TypeError):
                        continue
                    
                    total_vol += float(market.get('volume', market.get('volumeNum', 0)))
                
                if not outcomes:
                    continue
                
                # Determine if binary: single market with Yes/No, or multiple markets but all have same structure
                is_binary = (
                    len(markets) == 1 and 
                    len(outcomes) == 2 and 
                    any('yes' in k.lower() or 'no' in k.lower() for k in outcomes)
                ) or (
                    len(markets) > 1 and 
                    len(outcomes) == 2 and 
                    all('yes' in k.lower() or 'no' in k.lower() for k in outcomes)
                )
                deadline = markets[0].get('endDate')
                if deadline and isinstance(deadline, str):
                    try:
                        deadline = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                    except:
                        deadline = None
                all_events.append({
                    'type': 'binary' if is_binary else 'multi-outcome',
                    'event_id': event.get('id', ''),
                    'title': event.get('title', event.get('question', '')),
                    'normalized_title': normalize_title(event.get('title', '')),
                    'outcomes': outcomes,
                    'volume_usd': total_vol,
                    'deadline': deadline
                })
            if len(data) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"  [ERROR] {e}")
            break

    binary = sum(1 for e in all_events if e['type'] == 'binary')
    multi = len(all_events) - binary
    print(f"  -> Found {len(all_events)} events ({binary} binary, {multi} multi-outcome)")
    return all_events


def match_events(opinion_markets: List[Dict], poly_events: List[Dict]) -> List[Dict]:
    print(f"\n-> Matching {len(opinion_markets)} Opinion markets against {len(poly_events)} Polymarket events...")
    matches = []
    matched_poly = set()
    matched_opinion = set()

    poly_titles = [e['normalized_title'] for e in poly_events]
    poly_list = poly_events

    for op in opinion_markets:
        if op['event_id'] in matched_opinion:
            continue
        best = process.extractOne(op['normalized_title'], poly_titles, scorer=fuzz.token_set_ratio)
        if best and best[1] >= FUZZY_MATCH_THRESHOLD:
            score, idx = best[1], best[2]
            poly = poly_list[idx]
            if poly['event_id'] in matched_poly:
                continue
            matches.append({
                'match_title': op['title'],
                'match_score': score,
                'match_type': op['type'],
                'opinion': op,
                'polymarket': poly
            })
            matched_poly.add(poly['event_id'])
            matched_opinion.add(op['event_id'])

    binary = sum(1 for m in matches if m['match_type'] == 'binary')
    multi = len(matches) - binary
    print(f"  -> Found {len(matches)} matching events ({binary} binary, {multi} multi-outcome)")
    return matches


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_opinion_orderbook(token_id: str) -> Optional[Dict]:
    time.sleep(OPINION_RATE_LIMIT_DELAY)
    headers = {"apikey": OPINION_API_KEY}
    params = {"token_id": token_id}
    try:
        response = requests.get(f"{OPINION_BASE_URL}/token/orderbook", headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get('errno', -1) != 0:
            return None
        result = data.get('result', {})
        bids = result.get('bids', [])
        asks = result.get('asks', [])
        if not bids or not asks:
            return None
        # Best bid is the highest price you can sell at
        best_bid = max(bids, key=lambda x: float(x.get('price', 0)))
        # Best ask is the lowest price you can buy at
        best_ask = min(asks, key=lambda x: float(x.get('price', 0)))
        bid_price = normalize_price(float(best_bid.get('price', 0)))
        ask_price = normalize_price(float(best_ask.get('price', 0)))

        bid_depth = 0
        for b in bids[:20]:
            size = float(b.get('size', 0))
            price = normalize_price(float(b.get('price', 0)))
            depth_contrib = size * price
            if bid_depth + depth_contrib <= MAX_DEPTH_USDC:
                bid_depth += depth_contrib
            else:
                remaining = MAX_DEPTH_USDC - bid_depth
                bid_depth += min(remaining, depth_contrib)
                break

        ask_depth = 0
        for a in asks[:20]:
            size = float(a.get('size', 0))
            price = normalize_price(float(a.get('price', 0)))
            depth_contrib = size * price
            if ask_depth + depth_contrib <= MAX_DEPTH_USDC:
                ask_depth += depth_contrib
            else:
                remaining = MAX_DEPTH_USDC - ask_depth
                ask_depth += min(remaining, depth_contrib)
                break
        return {'best_bid': bid_price, 'best_ask': ask_price, 'bid_depth_usdc': bid_depth, 'ask_depth_usdc': ask_depth}
    except (requests.RequestException, ValueError, KeyError) as e:
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_polymarket_orderbook(token_id: str) -> Optional[Dict]:
    params = {"token_id": token_id, "limit": 20}
    try:
        response = requests.get(f"{POLY_CLOB_API}/book", params=params, timeout=5)
        response.raise_for_status()
        book = response.json()
        bids = book.get('bids', [])
        asks = book.get('asks', [])
        if not bids or not asks:
            return None
        best_bid = max(bids, key=lambda x: float(x.get('price', 0)))
        best_ask = min(asks, key=lambda x: float(x.get('price', 0)))
        bid_price = normalize_price(float(best_bid.get('price', 0)))
        ask_price = normalize_price(float(best_ask.get('price', 0)))
        bid_depth = 0
        for b in bids[:20]:
            size = float(b.get('size', 0))
            price = normalize_price(float(b.get('price', 0)))
            depth_contrib = size * price
            if bid_depth + depth_contrib <= MAX_DEPTH_USDC:
                bid_depth += depth_contrib
            else:
                remaining = MAX_DEPTH_USDC - bid_depth
                bid_depth += min(remaining, depth_contrib)
                break
        ask_depth = 0
        for a in asks[:20]:
            size = float(a.get('size', 0))
            price = normalize_price(float(a.get('price', 0)))
            depth_contrib = size * price
            if ask_depth + depth_contrib <= MAX_DEPTH_USDC:
                ask_depth += depth_contrib
            else:
                remaining = MAX_DEPTH_USDC - ask_depth
                ask_depth += min(remaining, depth_contrib)
                break
        return {'best_bid': bid_price, 'best_ask': ask_price, 'bid_depth_usdc': min(bid_depth, MAX_DEPTH_USDC), 'ask_depth_usdc': min(ask_depth, MAX_DEPTH_USDC)}
    except (requests.RequestException, ValueError, KeyError) as e:
        return None


def calculate_binary_arbitrage(o_yes: Dict, o_no: Dict, p_yes: Dict, p_no: Dict, tradeable_notional: float = 100.0) -> Optional[Dict]:
    """
    Calculate binary arbitrage opportunity with fee consideration.
    Polymarket: 0% fees
    Opinion.Trade: variable taker fees (0-2%), calculated per trade
    """
    if not all([o_yes, o_no, p_yes, p_no]):
        return None

    oy_ask = o_yes['best_ask']
    on_ask = o_no['best_ask']
    py_ask = p_yes['best_ask']
    pn_ask = p_no['best_ask']

    # Path A: Buy Opinion Yes + Buy Poly No
    depth_a = min(o_yes['ask_depth_usdc'], p_no['ask_depth_usdc'])
    notional_a = min(depth_a, tradeable_notional)
    opinion_fee_a = calculate_opinion_fee(oy_ask, notional_a * oy_ask)
    cost_a = oy_ask + pn_ask + opinion_fee_a  # Poly has 0% fee
    roi_a = (1 - cost_a) * 100 if cost_a < 1 else None

    # Path B: Buy Poly Yes + Buy Opinion No
    depth_b = min(p_yes['ask_depth_usdc'], o_no['ask_depth_usdc'])
    notional_b = min(depth_b, tradeable_notional)
    opinion_fee_b = calculate_opinion_fee(on_ask, notional_b * on_ask)
    cost_b = py_ask + on_ask + opinion_fee_b  # Poly has 0% fee
    roi_b = (1 - cost_b) * 100 if cost_b < 1 else None

    # Select best path
    best = None
    if roi_a is not None and roi_a > 0:
        best = {
            'roi_pct': roi_a,
            'roi_before_fees': (1 - (oy_ask + pn_ask)) * 100,
            'total_cost': cost_a,
            'tradeable_usdc': depth_a,
            'arb_strategy': 'Buy Opinion Yes + Buy Poly No',
            'cheap_platform': 'Opinion',
            'prices': f"O_Y={oy_ask:.4f}, P_N={pn_ask:.4f}, fee={opinion_fee_a:.4f}"
        }
    if roi_b is not None and roi_b > 0:
        if best is None or roi_b > best['roi_pct']:
            best = {
                'roi_pct': roi_b,
                'roi_before_fees': (1 - (py_ask + on_ask)) * 100,
                'total_cost': cost_b,
                'tradeable_usdc': depth_b,
                'arb_strategy': 'Buy Poly Yes + Buy Opinion No',
                'cheap_platform': 'Polymarket',
                'prices': f"P_Y={py_ask:.4f}, O_N={on_ask:.4f}, fee={opinion_fee_b:.4f}"
            }
    return best


def calculate_time_to_exp(deadline) -> Optional[int]:
    if not deadline:
        return None
    try:
        if isinstance(deadline, (int, float)):
            dt = datetime.fromtimestamp(deadline, tz=timezone.utc)
        elif isinstance(deadline, str):
            dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        elif isinstance(deadline, datetime):
            dt = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        else:
            return None
        return max(0, (dt - datetime.now(timezone.utc)).days)
    except (ValueError, OSError, OverflowError):
        return None


def main():
    print("=" * 80)
    print("Polymarket/Opinion.Trade Arbitrage Scanner")
    print("=" * 80)
    if not OPINION_API_KEY:
        print("ERROR: Set OPINION_API_KEY in .env")
        return

    opinion_markets = fetch_opinion_markets()
    poly_events = fetch_polymarket_events()
    if not opinion_markets or not poly_events:
        return

    matches = match_events(opinion_markets, poly_events)
    if not matches:
        return

    print(f"\n-> Analyzing {len(matches)} matches...")
    opportunities = []
    for i, match in enumerate(matches, 1):
        if i % 10 == 0:
            print(f"  Processing {i}/{len(matches)}...")
        op = match['opinion']
        poly = match['polymarket']

        # Determine if we can treat as binary (both venues have Yes/No structure)
        op_has_binary = op['type'] == 'binary' and 'Yes' in op.get('outcomes', {}) and 'No' in op.get('outcomes', {})
        p_outcomes_items = list(poly.get('outcomes', {}).items())
        p_yes_token = next((t for o, t in p_outcomes_items if 'yes' in o.lower()), None)
        p_no_token = next((t for o, t in p_outcomes_items if 'no' in o.lower()), None)
        # Fallback: if exactly 2 outcomes and neither matched yes/no, assume first=Yes, second=No
        if (not p_yes_token or not p_no_token) and len(p_outcomes_items) == 2:
            p_yes_token = p_outcomes_items[0][1]
            p_no_token = p_outcomes_items[1][1]
        poly_has_binary = p_yes_token is not None and p_no_token is not None

        # --- BINARY ARBITRAGE ---
        if op_has_binary and poly_has_binary:
            o_yes = fetch_opinion_orderbook(op['outcomes']['Yes'])
            o_no = fetch_opinion_orderbook(op['outcomes']['No'])

            if not all([o_yes, o_no, p_yes_token, p_no_token]):
                continue

            p_yes = fetch_polymarket_orderbook(p_yes_token)
            p_no = fetch_polymarket_orderbook(p_no_token)
            arb = calculate_binary_arbitrage(o_yes, o_no, p_yes, p_no)
            if arb and arb['roi_pct'] >= ARB_THRESHOLD_PCT:
                opportunities.append({
                    'title': match['match_title'],
                    'type': 'binary',
                    'ROI %': round(arb['roi_pct'], 2),
                    'total_cost': round(arb['total_cost'], 4),
                    'tradeable_usdc': round(arb['tradeable_usdc'], 2),
                    'arb_strategy': arb['arb_strategy'],
                    'prices': arb.get('prices'),
                    'opinion_id': op['event_id'],
                    'poly_id': poly['event_id'],
                    'time_to_exp_days': calculate_time_to_exp(op.get('deadline') or poly.get('deadline')),
                    'match_score': match['match_score']
                })

        # --- MULTI-OUTCOME ARBITRAGE (BUY-ONLY, NO SHORTING) ---
        else:
            # For multi-outcome, we check three strategies:
            # 1. Buy all outcomes on Opinion (single-venue surebet)
            # 2. Buy all outcomes on Polymarket (single-venue surebet)
            # 3. Cross-venue: buy cheapest ask for each outcome across both venues

            op_outcomes = op.get('outcomes', {})
            poly_outcomes = poly.get('outcomes', {})

            # CRITICAL: Check if outcomes are mutually exclusive
            # If not (e.g., nested time windows like "by March" / "by June"), skip
            op_outcome_names = list(op_outcomes.keys())
            poly_outcome_names = list(poly_outcomes.keys())

            op_exclusive, op_reason = are_outcomes_mutually_exclusive(op_outcome_names)
            poly_exclusive, poly_reason = are_outcomes_mutually_exclusive(poly_outcome_names)

            if not op_exclusive and not poly_exclusive:
                # Neither venue has exclusive outcomes - skip entirely
                continue

            # Fetch all orderbooks for Opinion outcomes
            op_orderbooks = {}  # outcome_name -> orderbook
            op_ok = True
            for name, tid in op_outcomes.items():
                ob = fetch_opinion_orderbook(tid)
                if ob:
                    op_orderbooks[name] = ob
                else:
                    op_ok = False

            # Fetch all orderbooks for Polymarket outcomes
            poly_orderbooks = {}  # outcome_name -> orderbook
            poly_ok = True
            for name, tid in poly_outcomes.items():
                ob = fetch_polymarket_orderbook(tid)
                if ob:
                    poly_orderbooks[name] = ob
                else:
                    poly_ok = False

            # --- Strategy 1: Buy all on Opinion ---
            # Only valid if Opinion outcomes are mutually exclusive
            if op_exclusive and op_ok and len(op_orderbooks) >= 2:
                op_total_cost = 0.0
                op_total_fee = 0.0
                op_min_depth = MAX_DEPTH_USDC
                for name, ob in op_orderbooks.items():
                    ask = ob['best_ask']  # Already normalized
                    depth = ob['ask_depth_usdc']
                    fee = calculate_opinion_fee(ask, depth * ask)
                    op_total_cost += ask
                    op_total_fee += fee
                    op_min_depth = min(op_min_depth, depth)

                cost_with_fees = op_total_cost + op_total_fee
                if cost_with_fees < 1.0:
                    roi = (1.0 - cost_with_fees) * 100.0
                    if roi >= ARB_THRESHOLD_PCT:
                        opportunities.append({
                            'title': match['match_title'],
                            'type': 'multi-outcome',
                            'ROI %': round(roi, 2),
                            'total_cost': round(cost_with_fees, 4),
                            'tradeable_usdc': round(op_min_depth, 2),
                            'arb_strategy': f'Buy all {len(op_orderbooks)} outcomes on Opinion',
                            'prices': f"sum_asks={op_total_cost:.4f}, fees={op_total_fee:.4f}",
                            'opinion_id': op['event_id'],
                            'poly_id': poly['event_id'],
                            'time_to_exp_days': calculate_time_to_exp(op.get('deadline')),
                            'match_score': match['match_score']
                        })

            # --- Strategy 2: Buy all on Polymarket (0% fees) ---
            # Only valid if Polymarket outcomes are mutually exclusive
            if poly_exclusive and poly_ok and len(poly_orderbooks) >= 2:
                poly_total_cost = 0.0
                poly_min_depth = MAX_DEPTH_USDC
                for name, ob in poly_orderbooks.items():
                    ask = ob['best_ask']  # Already normalized
                    depth = ob['ask_depth_usdc']
                    poly_total_cost += ask
                    poly_min_depth = min(poly_min_depth, depth)

                if poly_total_cost < 1.0:
                    roi = (1.0 - poly_total_cost) * 100.0
                    if roi >= ARB_THRESHOLD_PCT:
                        opportunities.append({
                            'title': match['match_title'],
                            'type': 'multi-outcome',
                            'ROI %': round(roi, 2),
                            'total_cost': round(poly_total_cost, 4),
                            'tradeable_usdc': round(poly_min_depth, 2),
                            'arb_strategy': f'Buy all {len(poly_orderbooks)} outcomes on Polymarket',
                            'prices': f"sum_asks={poly_total_cost:.4f}",
                            'opinion_id': op['event_id'],
                            'poly_id': poly['event_id'],
                            'time_to_exp_days': calculate_time_to_exp(poly.get('deadline')),
                            'match_score': match['match_score']
                        })

            # --- Strategy 3: Cross-venue (buy cheapest per outcome) ---
            # Match outcomes between venues using fuzzy matching
            # Both venues must have mutually exclusive outcomes for cross-venue to be valid
            if op_exclusive and poly_exclusive and op_ok and poly_ok and len(op_orderbooks) >= 2 and len(poly_orderbooks) >= 2:
                # Try to match each Opinion outcome to a Polymarket outcome
                # Use orderbook keys since we need outcomes with valid orderbooks
                op_names_with_books = list(op_orderbooks.keys())
                poly_names_with_books = list(poly_orderbooks.keys())
                matched_outcomes = []  # list of (op_name, poly_name, best_ask, best_venue, depth)
                used_poly = set()

                for op_name in op_names_with_books:
                    # Fuzzy match to find corresponding Poly outcome
                    best_match = process.extractOne(
                        normalize_title(op_name),
                        [normalize_title(p) for p in poly_names_with_books if p not in used_poly],
                        scorer=fuzz.token_set_ratio
                    )
                    if best_match and best_match[1] >= 70:  # Lower threshold for outcome matching
                        poly_idx = [normalize_title(p) for p in poly_names_with_books].index(best_match[0])
                        poly_name = poly_names_with_books[poly_idx]
                        if poly_name in used_poly:
                            continue
                        used_poly.add(poly_name)

                        op_ob = op_orderbooks[op_name]
                        poly_ob = poly_orderbooks[poly_name]

                        op_ask = op_ob['best_ask']
                        poly_ask = poly_ob['best_ask']

                        # Include Opinion fee in comparison
                        op_fee = calculate_opinion_fee(op_ask, min(op_ob['ask_depth_usdc'], MAX_DEPTH_USDC) * op_ask)
                        op_effective = op_ask + op_fee

                        if poly_ask <= op_effective:
                            matched_outcomes.append({
                                'op_name': op_name,
                                'poly_name': poly_name,
                                'best_ask': poly_ask,
                                'venue': 'Poly',
                                'depth': poly_ob['ask_depth_usdc']
                            })
                        else:
                            matched_outcomes.append({
                                'op_name': op_name,
                                'poly_name': poly_name,
                                'best_ask': op_effective,
                                'venue': 'Opinion',
                                'depth': op_ob['ask_depth_usdc']
                            })

                # If we matched all outcomes, check for cross-venue arb
                if len(matched_outcomes) == len(op_names_with_books) and len(matched_outcomes) >= 2:
                    cross_total = sum(m['best_ask'] for m in matched_outcomes)
                    cross_min_depth = min(m['depth'] for m in matched_outcomes)
                    venues_used = set(m['venue'] for m in matched_outcomes)

                    # Only report if actually cross-venue (uses both)
                    if len(venues_used) == 2 and cross_total < 1.0:
                        roi = (1.0 - cross_total) * 100.0
                        if roi >= ARB_THRESHOLD_PCT:
                            venue_breakdown = ', '.join(f"{m['op_name'][:15]}@{m['venue']}" for m in matched_outcomes[:3])
                            if len(matched_outcomes) > 3:
                                venue_breakdown += f"... +{len(matched_outcomes)-3} more"
                            opportunities.append({
                                'title': match['match_title'],
                                'type': 'multi-outcome-cross',
                                'ROI %': round(roi, 2),
                                'total_cost': round(cross_total, 4),
                                'tradeable_usdc': round(cross_min_depth, 2),
                                'arb_strategy': f'Cross-venue: {len(matched_outcomes)} outcomes',
                                'prices': venue_breakdown,
                                'opinion_id': op['event_id'],
                                'poly_id': poly['event_id'],
                                'time_to_exp_days': calculate_time_to_exp(op.get('deadline') or poly.get('deadline')),
                                'match_score': match['match_score']
                            })

    if not opportunities:
        print(f"\nNo arbs > {ARB_THRESHOLD_PCT}% ROI")
        return

    df = pd.DataFrame(opportunities).sort_values('ROI %', ascending=False)
    print("\n" + "=" * 100)
    print(f"ARBITRAGE OPPORTUNITIES (ROI > {ARB_THRESHOLD_PCT}%)")
    print("=" * 100)
    display_df = df.copy()
    display_df['ROI %'] = display_df['ROI %'].apply(lambda x: f"{x:.2f}%")
    display_df['tradeable_usdc'] = display_df['tradeable_usdc'].apply(lambda x: f"${x:,.2f}")
    
    # Custom column order for display
    cols = ['title', 'type', 'ROI %', 'total_cost', 'tradeable_usdc', 'arb_strategy', 'prices', 'match_score', 'time_to_exp_days', 'opinion_id', 'poly_id']
    display_df = display_df[[c for c in cols if c in display_df.columns]]
    
    # Increase print width to accommodate long titles/strategies
    pd.set_option('display.max_colwidth', None)
    
    print(display_df.to_string(index=False))
    print("=" * 100)
    df.to_csv('arbs.csv', index=False)
    print(f"\nSaved to arbs.csv | Found {len(opportunities)} opportunities")


if __name__ == '__main__':
    main()