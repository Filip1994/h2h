# Market Timing Intelligence

Issue #44 adds an observational market-timing layer around the existing Dixon-Coles/value pipeline.

## What is collected

`data/market_timing_snapshots.jsonl` stores immutable observations for eligible predicted fixtures whenever the adaptive Watchlist obtains a valid quote:

- fixture and prediction IDs
- league, market, bookmaker and kickoff
- capture timestamp and time-to-kickoff
- selected and opposite odds
- market overround and devig probability
- model/calibrated/decision probabilities
- EV and probability edge
- observation state: `OBSERVED`, `NEAR_MISS`, or `STRONG`

`market_timing_metrics.json` exposes per-run snapshot counts, useful observations and API requests per useful observation.

## Sampling policy

The Watchlist is now scheduled every two minutes during the active window, while each fixture keeps an adaptive cadence:

- >6h: 60m
- 3–6h: 30m
- 2–3h: 15m
- 1–2h: 10m
- 30–60m: 5m
- 10–30m: 3m
- ≤10m: 2m

This increases observation density where market timing is most informative without introducing a universal betting-time rule. The existing API budget and reserve remain enforced.

## Research-ready lifecycle

The snapshot stream can later be joined to alerts/bets using fixture, prediction, market and bookmaker identifiers. This supports first detection, persistence, disappearance/reappearance, best observed value, bet-time value, closing value and CLV analysis where those downstream records exist.

No model, calibration, EV, league eligibility, staking or automatic betting policy is changed by this issue.
