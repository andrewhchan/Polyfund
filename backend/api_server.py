from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from .belief_selection import select_anchor_market, AnchorMarket
from .correlation import (
    compute_correlation_matrix,
    construct_portfolio,
    generate_signals,
    MIN_OVERLAPPING_DAYS,
)
from .llm_proxy import generate_proxy_theses
from .market_data import fetch_price_history, HISTORY_DAYS
from .portfolio_output import generate_portfolio_timeseries
from .search_pipeline import discover_markets

CONFIDENCE_THRESHOLD = 0.90


class RecommendationRequest(BaseModel):
    thesis: str
    days: int = HISTORY_DAYS
    top_k: int = 100
    keyword_match_threshold: int = 70


app = FastAPI(title="Polymarket Quant API", version="0.1.0")
load_dotenv()


def _anchor_to_dict(anchor: AnchorMarket) -> Dict[str, Any]:
    slug = anchor.market.get("slug")
    if not slug and "event" in anchor.market:
        slug = anchor.market["event"].get("slug")

    return {
        "question": anchor.market.get("question"),
        "slug": slug,
        "token_id": anchor.token_id,
        "volume_usd": anchor.market.get("volume_usd"),
        "token_choice": anchor.token_choice,
        "ai_reasoning": anchor.reasoning,
        "ai_confidence": anchor.confidence,
    }


def _df_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    return df.to_dict(orient="records") if df is not None and not df.empty else []


def _error_payload(thesis: str, stage: str, message: str, explain: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build a consistent error payload with 200 status so clients can handle gracefully.
    """
    return {
        "thesis": thesis,
        "status": "error",
        "error_stage": stage,
        "error_message": message,
        "anchor": None,
        "portfolio": [],
        "signals": [],
        "explain": explain or {},
    }


def build_recommendations(req: RecommendationRequest) -> Dict[str, Any]:
    # Step 1: discover markets from Supabase
    markets, explain = discover_markets(
        req.thesis,
        k=req.top_k,
        keyword_match_threshold=req.keyword_match_threshold,
        allow_fallback=True,
    )
    
    # Pre-process markets to Ensure slug is available (it might be nested in 'event')
    if markets:
        for m in markets:
            if not m.get("slug") and "event" in m:
                m["slug"] = m["event"].get("slug")

    if not markets:
        return _error_payload(req.thesis, "discover_markets", "No markets found for thesis", explain)

    # Step 2: anchor selection
    anchor = select_anchor_market(markets, req.thesis)

    # Step 3: retry with proxy theses if confidence is low
    if anchor is None or anchor.confidence < CONFIDENCE_THRESHOLD:
        alt_theses = generate_proxy_theses(req.thesis)
        alt_markets: List[Dict[str, Any]] = []
        seen_conditions = {m["condition_id"] for m in markets}
        for alt in alt_theses:
            alt_found, _ = discover_markets(
                alt,
                k=req.top_k,
                keyword_match_threshold=req.keyword_match_threshold,
                allow_fallback=False,
            )
            for m in alt_found:
                cid = m.get("condition_id")
                if cid and cid not in seen_conditions:
                    seen_conditions.add(cid)
                    alt_markets.append(m)
            if alt_markets:
                # Ensure slugs are populated for new markets
                for m in alt_markets:
                    if not m.get("slug") and "event" in m:
                        m["slug"] = m["event"].get("slug")
                        
                markets = alt_markets
                anchor = select_anchor_market(markets, req.thesis)

    if anchor is None or anchor.confidence < CONFIDENCE_THRESHOLD:
        from .belief_selection import select_arbitrary_bets
        arbitrary_bets = select_arbitrary_bets(markets, req.thesis, k=10)
        
        return {
            "thesis": req.thesis,
            "status": "ok",
            "warning": "Thesis is too far off an existing market for data analysis.",
            "anchor": None,
            "portfolio": arbitrary_bets,
            "signals": [],
            "timeseries": {
                "metadata": {"thesis": req.thesis},
                "price_series": {"anchor": [], "candidates": {}},
                "rolling_correlations": {},
                "pnl_curves": {"portfolio": [], "positions": {}}
            },
            "explain": explain,
        }

    # Build lookup for metadata
    markets_lookup = {m["yes_token_id"]: m for m in markets if m.get("yes_token_id")}
    for m in markets:
        if m.get("no_token_id"):
            markets_lookup[m["no_token_id"]] = m

    # Step 4: price history
    anchor_series = fetch_price_history(anchor.token_id, days=req.days)
    if anchor_series is None or len(anchor_series) < MIN_OVERLAPPING_DAYS:
        return _error_payload(req.thesis, "anchor_history", "Insufficient anchor price history", explain)

    candidate_series: Dict[str, pd.Series] = {}
    for m in markets:
        yes_id = m.get("yes_token_id")
        no_id = m.get("no_token_id")
        # skip anchor token
        if yes_id == anchor.token_id or no_id == anchor.token_id:
            continue
        series = fetch_price_history(yes_id, days=req.days)
        if series is not None and len(series) >= MIN_OVERLAPPING_DAYS:
            candidate_series[yes_id] = series

    if not candidate_series:
        return _error_payload(req.thesis, "candidate_history", "No candidate price histories", explain)

    # Step 5: correlations and signals
    corr_df = compute_correlation_matrix(anchor_series, candidate_series)
    if corr_df.empty:
        return _error_payload(req.thesis, "correlation", "No correlations computed", explain)

    signals_df = generate_signals(corr_df, markets_lookup)
    if signals_df.empty:
        return _error_payload(req.thesis, "signals", "No markets meet correlation thresholds", explain)

    portfolio_df = construct_portfolio(signals_df)

    # Step 6: Generate time-series data for visualization (re-using existing series)
    timeseries_data = generate_portfolio_timeseries(
        portfolio_df=portfolio_df,
        anchor=_anchor_to_dict(anchor),
        thesis=req.thesis,
        anchor_series=anchor_series,
        candidate_series=candidate_series,
        windows=[7, 14, 30]
    )

    return {
        "thesis": req.thesis,
        "status": "ok",
        "anchor": _anchor_to_dict(anchor),
        "portfolio": _df_records(portfolio_df),
        "signals": _df_records(signals_df),
        "timeseries": timeseries_data,
        "explain": explain,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/recommendations")
def recommendations(req: RecommendationRequest):
    return build_recommendations(req)
