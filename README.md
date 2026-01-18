# Polymarket Correlation-Aware Trade Recommendation Engine

FastAPI backend that discovers Polymarket markets for a free-text thesis, selects a belief market, computes historical co-movement correlations, and returns recommendations plus time-series artifacts for visualization.

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

## Run

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

## Tests

```bash
pytest
```
