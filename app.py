import os
from typing import Dict, List, Any

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from belief_selection import find_belief_market_semantic
from correlation import (
    compute_correlation_matrix,
    construct_portfolio,
)
from market_data import fetch_price_history
from mock_ai import MockAIBeliefAnalyzer
from portfolio_output import save_portfolio_json
from search_pipeline import discover_markets


app = FastAPI(title="Polymarket Correlation-Aware Trade Recommendation Engine")


def _fetch_histories(markets: List[Dict[str, Any]], days: int) -> Dict[str, pd.Series]:
    series_map: Dict[str, pd.Series] = {}
    for m in markets:
        token_id = m.get("token_id")
        if not token_id:
            continue
        series = fetch_price_history(token_id, days=days)
        if series is not None and not series.empty:
            series_map[token_id] = series
    return series_map


def _compute_returns(series: pd.Series) -> pd.Series:
    return series.pct_change().dropna()


def _action_for_corr(r: float) -> str:
    if r > 0.6:
        return "momentum_with_belief"
    if r > 0.3:
        return "mild_with_belief"
    if r < -0.6:
        return "hedge_against_belief"
    if r < -0.3:
        return "mild_against_belief"
    return "watchlist"


@app.post("/api/search/smart")
def smart_search(payload: Dict[str, Any]):
    query = payload.get("query")
    k = int(payload.get("k", 30))
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")

    candidates, explain = discover_markets(query, k=k)
    return JSONResponse(
        {
            "query": query,
            "keywords": explain["keywords"],
            "candidates": candidates,
            "explain": explain,
        }
    )


@app.post("/api/recommendations")
def recommendations(payload: Dict[str, Any]):
    query = payload.get("query")
    days = int(payload.get("days", 30))
    top_n = int(payload.get("top_n", 20))
    min_points = int(payload.get("min_points", 20))
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")

    candidates, explain = discover_markets(query, k=top_n * 3)

    ai_analyzer = MockAIBeliefAnalyzer()
    anchor = find_belief_market_semantic(candidates, query, ai_analyzer)
    if not anchor:
        raise HTTPException(status_code=404, detail="No belief market found")

    histories = _fetch_histories(candidates, days=days)
    belief_series = histories.get(anchor["token_id"])
    if belief_series is None:
        raise HTTPException(status_code=404, detail="No price history for belief market")

    # Compute returns for correlation stability
    belief_returns = _compute_returns(belief_series)
    candidate_returns = {}
    for token_id, series in histories.items():
        if token_id == anchor["token_id"]:
            continue
        returns = _compute_returns(series)
        if len(returns) >= min_points:
            candidate_returns[token_id] = returns

    corr_df = compute_correlation_matrix(belief_returns, candidate_returns)
    if corr_df.empty:
        raise HTTPException(status_code=404, detail="No correlated markets found")

    # Attach metadata and filter by overlap
    markets_lookup = {m["token_id"]: m for m in candidates}
    corr_df = corr_df[corr_df["n_points"] >= min_points]
    corr_df = corr_df.sort_values("correlation", ascending=False)

    related = []
    for _, row in corr_df.head(top_n).iterrows():
        m = markets_lookup.get(row["token_id"], {})
        related.append(
            {
                "condition_id": m.get("condition_id"),
                "question": m.get("question"),
                "corr": row["correlation"],
                "n_points": int(row["n_points"]),
                "liquidity": m.get("volume_usd"),
                "action": _action_for_corr(row["correlation"]),
                "why": "historical co-movement (not causation)",
            }
        )

    # Correlation matrix for top markets
    top_tokens = [r["condition_id"] for r in related if r.get("condition_id")]  # reuse condition ids as labels
    matrix_df = corr_df[corr_df["token_id"].isin([m.get("token_id") for m in markets_lookup.values()])]
    # simple pairwise: belief vs each; full matrix optional
    corr_matrix = {
        "markets": top_tokens,
        "matrix": [[row["correlation"]] for _, row in corr_df.head(len(top_tokens)).iterrows()],
    }

    # Optional portfolio suggestion (heuristic)
    signals = corr_df.copy()
    signals.rename(columns={"correlation": "signal_strength"}, inplace=True)
    signals["action"] = ["BUY YES" if r > 0 else "BUY NO" for r in signals["signal_strength"]]
    signals["volume_usd"] = signals["token_id"].map(lambda t: markets_lookup.get(t, {}).get("volume_usd", 0))
    portfolio_df = construct_portfolio(signals)

    explain["window_days"] = days
    explain["min_points"] = min_points
    explain["notes"] = ["correlations are historical co-movement, not causation"]

    # Save JSON artifact for visualization
    candidate_series_full = {t: s for t, s in histories.items() if t != anchor["token_id"]}
    save_portfolio_json(
        portfolio_df=portfolio_df,
        belief=anchor,
        thesis=query,
        belief_series=belief_series,
        candidate_series=candidate_series_full,
        windows=(7, 14, 30),
    )

    return JSONResponse(
        {
            "query": query,
            "anchor": anchor,
            "related": related,
            "corr_matrix": corr_matrix,
            "explain": explain,
        }
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
