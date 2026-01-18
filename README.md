# Polymarket Correlation-Aware Trade Recommendation Engine

FastAPI backend (under `backend/`) that discovers Polymarket markets for a free-text thesis, selects a belief market, computes historical co-movement correlations, and returns recommendations plus time-series artifacts for visualization.

## Endpoints

- `POST /api/search/smart`
  - Body: `{"query": "...", "k": 30}`
  - Returns generated keywords, discovered candidate markets, and explain metadata.

- `POST /api/recommendations`
  - Body: `{"query": "...", "days": 30, "top_n": 20, "min_points": 20}`
  - Runs smart search, selects anchor belief, fetches price histories, computes correlations (on returns), filters by overlap/liquidity, and returns related markets with actions. Saves a `quant_basket_<thesis>_timeseries.json` artifact with rolling correlations, price paths, and P&L curves.

## Config

- `POLYMARKET_GAMMA_BASE_URL` (default: https://gamma-api.polymarket.com)
- `POLYMARKET_CLOB_BASE_URL` (default: https://clob.polymarket.com)
- `OPENAI_API_KEY` (optional; keyword generation uses mock fallback if missing)
- `GEMINI_API_KEY` (optional; keyword generation uses mock fallback if missing)
- `LLM_PROVIDER` (`openai` | `gemini` | `mock`, default mock)
- LLM fallback: If no close market matches (keyword threshold default 70), proxy theses are generated to re-run search.
- `DATABASE_URL` or `SUPABASE_DB_URL` (optional): Postgres connection; if set, discovery will search the `markets` table before hitting Gamma.

## Run

Using `uv` (recommended):
```bash
uv sync
uv run uvicorn backend.api_server:app --reload
# or legacy shim: uv run uvicorn api_server:app --reload
# CLI: uv run python -m backend.main "Lakers good season"
```

## ETL: load markets into Postgres

1) Ensure `DATABASE_URL` (or `SUPABASE_DB_URL`) points to your Postgres with the `markets` table (see schema in earlier response).
2) Run the ingest (defaults to 1000 markets; adjust `--limit` and `--batch-size`):
```bash
uv run python etl_markets.py --limit 1000 --batch-size 500
```
Set `POLYMARKET_GAMMA_BASE_URL` if you need a non-default endpoint.

## Tests

```bash
pytest
```
