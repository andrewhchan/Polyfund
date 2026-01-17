# Polymarket Challenge Prompt

Polymarket is the world's largest prediction market where traders predict the outcome of future events across politics, current events, pop culture, and more, winning when they're right. As traders react to breaking news in real-time, market prices become the most accurate gauge of event likelihood, which institutions, individuals, and the media rely on to report news and better understand the future. With billions of dollars in predictions made in 2025 and exclusive partnerships with the Wall Street Journal, UFC, Golden Globes, and New York Rangers, Polymarket has established itself as the definitive platform for real-time forecasting and market-driven insights.

## Challenge Prompt

Prediction markets are powerful financial derivatives, especially for hedging exposure and constructing sophisticated strategies, but most users still interact with them using relatively simple interfaces. In traditional finance, traders rely on sophisticated tooling like profit & loss curves, scenario modeling, time-based payoff visualizations, and portfolio hedging views to deeply understand risk and opportunity before placing a trade. These tools are largely missing in prediction markets today.

Your challenge is to design and build advanced trading tools for Polymarket that help users better understand, visualize, and manage risk across time, price, and probability.

Participants should build applications that leverage Polymarket markets and data to create TradFi-style trading experiences, such as:

- Profit & loss visualizations across different probability outcomes and time horizons e.g. https://www.optionsprofitcalculator.com/
- Hedging tools that pair prediction markets with other speculative positions (e.g., options, perps, spot, or synthetic exposure)
- Scenario analysis tools that show how a position performs if an event resolves sooner vs later
- Portfolio or strategy views that combine multiple markets into a single payoff graph
- Educational visualizations that make complex strategies easier to understand and trade

The goal is to unlock more sophisticated trading behavior by making prediction markets easier to reason about, experiment with, and trust, especially for users coming from traditional trading or crypto-native derivatives.

## Project Requirements

- Use real or realistic Polymarket market data
- This can include live markets, historical market data, or clearly labeled simulated data derived from real Polymarket contracts. Assumptions and simplifications should be made explicit.
- Provide a functional demo with clear user interaction
- Submissions should allow a user to input positions, strategies, or parameters (e.g., probabilities, time horizons, multiple markets) and see outputs update dynamically.
- Produce concrete analytical or visual outputs
- Examples include (but are not limited to): payoff curves, scenario trees, time-based profit/loss charts, portfolio payoff surfaces, correlation views, inefficiency indicators, or strategy comparisons across markets.
- Be grounded in real trading use cases
- The tool should plausibly help a trader make better decisions, manage risk, identify inefficiencies, or understand tradeoffs before placing a trade.

Submissions can come in various forms, such as but not limited to web apps, dashboards, visual simulators, or analytical tools.

## Evaluation Criteria

We will prioritize projects that demonstrate:

- Quality of insight and correctness of modeling
- Sound reasoning around probabilities, payoffs, correlations, and resolution timing. Clear, defensible assumptions matter more than complexity for its own sake.
- Strength of visualization and user experience
- Interfaces that make complex strategies, risks, and tradeoffs intuitive and easy to understand. Great UX that helps users see what happens across time, price, and outcomes will be heavily rewarded.
- Technical depth and execution
- Thoughtful use of data, calculations, and system design. Bonus for handling multi-market interactions, non-mutually exclusive events, or correlated outcomes in a robust way.
- Real-world trading applicability
- The tool should plausibly help real traders make better decisions, manage risk, or identify inefficiencies.
- Creativity and originality
- Novel approaches to prediction market tooling, strategy construction, or educational visualization. We value new mental models and workflows, not clones of existing dashboards.
- Clarity of explanation
- Teams should be able to clearly explain what their tool does, why it matters, and how a trader would actually use it

## Resources

- Documentation: https://docs.polymarket.com/quickstart/overview
- API References:
  - CLOB endpoints: https://docs.polymarket.com/api-reference/orderbook/get-order-book-summary
  - Gamma endpoints: https://docs.polymarket.com/api-reference/gamma-status
  - Data API: https://docs.polymarket.com/api-reference/data-api-status/data-api-health-check
- Websockets:
  - https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- SDKs:
  - Typescript CLOB client: https://github.com/Polymarket/clob-client
  - Typescript Relay client: https://github.com/Polymarket/builder-relayer-client
  - Python CLOB client: https://github.com/Polymarket/py-clob-client
  - Python Relay client: https://github.com/Polymarket/py-builder-relayer-client
  - Rust Client (includes data endpoints and clob): https://github.com/Polymarket/rs-clob-client
- Example Repos / Demos:
  - WAGMI integration: https://github.com/Polymarket/wagmi-safe-builder-example
  - Privy integration: https://github.com/Polymarket/privy-safe-builder-example
  - Magic link integration: https://github.com/Polymarket/magic-safe-builder-example
  - Turnkey integration: https://github.com/Polymarket/turnkey-safe-builder-example

All integration examples include data fetching, placing order and other misc activities using Polymarket APIs

# Project Design Notes

## OVERVIEW

Goal: Given a thesis (e.g., "Democrats win 2026 Midterms"), build a Polymarket basket: choose a belief market that matches the thesis, find correlated markets, generate buy YES/NO signals, and output a weighted portfolio with a CSV.

## CURRENT MODULES (IN REPO)

- `market_data.py`: Fetch top liquid markets + price history from Polymarket.
- `belief_selection.py`: Fuzzy search + semantic selection of belief market.
- `mock_ai.py`: Heuristic intent alignment (placeholder for real LLM).
- `correlation.py`: Pearson correlation + signal generation + portfolio weights.
- `portfolio_output.py`: Console table + CSV output.

## PIPELINE (EXPECTED DATA FLOW)

Input thesis (string)  
→ Fetch related markets wrt to the belief (`fetch_polymarket_markets`)  
→ Select belief market (`find_belief_market_semantic`)  
→ Fetch belief price history + candidate histories (`fetch_price_history`)  
→ Compute correlation matrix (`compute_correlation_matrix`)  
→ Generate signals (`generate_signals`)  
→ Construct portfolio weights (`construct_portfolio`)  
→ Output (`print_portfolio_table`, `save_portfolio_csv`)

## DATA MODEL (KEY FIELDS)

Market object (from `market_data.py`):  
`condition_id`, `yes_token_id`, `no_token_id`, `token_id`, `question`, `event_title`, `volume_usd`, `outcome_yes_price`

Signal row (`correlation.py`):  
`token_id`, `question`, `correlation`, `action`, `signal_strength`, `n_data_points`, `volume_usd`

Portfolio row (post-weighting):  
All above + `weight`, `weight_pct`

## SCOPE

Must-have:
- End-to-end script that runs the pipeline for a thesis and saves CSV
- Belief selection with semantic alignment (mock AI OK)
- Correlation-based signals + weights
- Console + CSV output

Nice-to-have:
- Simple CLI flags (e.g., `--thesis`, `--days`, `--top_n`)
- Caching of price history to speed demo
- Replace MockAI with real LLM call
- Basic unit tests for belief selection + correlation logic

## RISKS / OPEN QUESTIONS

- Missing orchestrator script (likely `poly_quant_fund.py`) to wire modules
- API rate limits / incomplete price histories
- Thesis ambiguity (semantic alignment might select wrong token)
- Correlation on sparse data (min overlapping days = 10)

## TASK BREAKDOWN (4 PEOPLE)

Person A — Data & API
- Harden `fetch_polymarket_markets` and `fetch_price_history`
- Add optional caching (disk or in-memory)
- Add CLI flags for `--days`, `--top_n`
- Deliverables: data layer improvements + docs

Person B — Belief Selection & AI
- Remove fuzzy search thresholds + tie-breaking and use LLM instead to fetch related markets (given the entire market)
- Add "explain why" output for selected belief
- Deliverables: better belief selection + reasoning

Person C — Correlation & Portfolio
- Validate correlation math + thresholds
- Add filtering rules (min volume, min points)
- Portfolio weighting + ordering
- Deliverables: robust signal/portfolio logic

Person D — Orchestrator + Output
- Use privy/add UI
