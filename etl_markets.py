import argparse
import json
import os
from typing import Any, Dict, List

import requests
from sqlalchemy import text

from db import get_engine, get_supabase


GAMMA_BASE = os.getenv("POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com")
BATCH_SIZE = 500


def fetch_markets(limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    params = {
        "limit": limit,
        "offset": offset,
        "active": True,
        "closed": False,
        # "order": "volume_num",
        # "ascending": False,
    }
    resp = requests.get(f"{GAMMA_BASE}/markets", params=params, timeout=20)
    if resp.status_code == 422:
        # Retry without filters that may not be supported on this endpoint
        params = {"limit": limit, "offset": offset}
        resp = requests.get(f"{GAMMA_BASE}/markets", params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def parse_token_ids(raw: Any) -> List[str]:
    if raw is None:
        return []
    try:
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, list):
            return raw
    except Exception:
        return []
    return []


def to_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def flatten_market(m: Dict[str, Any]) -> Dict[str, Any]:
    token_ids = parse_token_ids(m.get("clobTokenIds"))
    yes_token_id = token_ids[0] if token_ids else None
    no_token_id = token_ids[1] if len(token_ids) > 1 else None
    volume = to_float(m.get("volumeNum") or m.get("volume"))
    liquidity = to_float(m.get("liquidityNum") or m.get("liquidity"))
    outcome_yes_price = 0.5
    prices = m.get("outcomePrices")
    if prices:
        try:
            if isinstance(prices, str):
                prices = prices.strip("[]").split(",")
            outcome_yes_price = float(prices[0])
        except Exception:
            pass

    return {
        "condition_id": m.get("conditionId"),
        "question": m.get("question") or "",
        "event_title": m.get("question") or "",
        "status": "open" if m.get("active") and not m.get("closed") else "closed",
        "end_date": m.get("endDate"),
        "volume_usd": volume,
        "liquidity": liquidity,
        "yes_token_id": yes_token_id,
        "no_token_id": no_token_id,
        "token_id": yes_token_id,
        "outcome_yes_price": outcome_yes_price,
        "raw": json.dumps(m),
    }


def upsert_markets(engine, markets: List[Dict[str, Any]]) -> None:
    if not markets:
        return
    stmt = text(
        """
        INSERT INTO markets (
            condition_id, question, event_title, status, end_date, volume_usd,
            liquidity, yes_token_id, no_token_id, token_id, outcome_yes_price, raw, updated_at
        ) VALUES (
            :condition_id, :question, :event_title, :status, :end_date, :volume_usd,
            :liquidity, :yes_token_id, :no_token_id, :token_id, :outcome_yes_price, :raw, NOW()
        )
        ON CONFLICT (condition_id) DO UPDATE SET
            question = EXCLUDED.question,
            event_title = EXCLUDED.event_title,
            status = EXCLUDED.status,
            end_date = EXCLUDED.end_date,
            volume_usd = EXCLUDED.volume_usd,
            liquidity = EXCLUDED.liquidity,
            yes_token_id = EXCLUDED.yes_token_id,
            no_token_id = EXCLUDED.no_token_id,
            token_id = EXCLUDED.token_id,
            outcome_yes_price = EXCLUDED.outcome_yes_price,
            raw = EXCLUDED.raw,
            updated_at = NOW();
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, markets)


def upsert_supabase(client, markets: List[Dict[str, Any]]) -> None:
    if not markets:
        return
    # Supabase upsert with on_conflict condition_id
    # Send in smaller chunks to avoid payload limits
    chunk_size = 500
    for i in range(0, len(markets), chunk_size):
        chunk = markets[i : i + chunk_size]
        client.table("markets").upsert(chunk, on_conflict="condition_id").execute()


def main():
    parser = argparse.ArgumentParser(description="Ingest Polymarket markets into Postgres.")
    parser.add_argument("--limit", type=int, default=1000, help="Total markets to fetch.")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Fetch batch size.")
    args = parser.parse_args()

    supabase_client = get_supabase()
    if not supabase_client:
        raise SystemExit("DATABASE_URL/SUPABASE_DB_URL or SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY must be set.")

    fetched = 0
    offset = 0
    total_target = args.limit
    batch_size = args.batch_size

    while fetched < total_target:
        remaining = total_target - fetched
        this_limit = min(batch_size, remaining)
        page = fetch_markets(limit=this_limit, offset=offset)
        if not page:
            break
        flattened = [f for f in (flatten_market(m) for m in page) if f.get("condition_id")]
        if supabase_client:
            upsert_supabase(supabase_client, flattened)
        fetched += len(flattened)
        offset += this_limit
        print(f"Ingested {fetched} markets...")
        if len(page) < this_limit:
            break

    print(f"Done. Total ingested: {fetched}")


if __name__ == "__main__":
    main()
