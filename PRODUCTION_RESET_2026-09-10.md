# QuantBet Production Reset — 2026-09-10

## The system now has one primary job

Produce Production paper picks, email them, observe the exact bookmaker odds, settle them, and show the hard data on one dashboard.

## Five things the dashboard answers

1. **What did Production pick?** — from `bets.json`.
2. **What was the Opening?** — first persisted observation for the exact fixture + market + bookmaker at or before Pick.
3. **What is Live?** — latest persisted observation for that exact fixture + market + bookmaker.
4. **What was Closing?** — latest persisted observation 2–8 minutes before kickoff.
5. **Did the bet win and what was CLV?** — settlement from Football API; CLV is Pick / Closing - 1 when Closing exists.

Missing data is `null` in the data and `—` in the UI. There are no bookmaker substitutions and no fabricated Opening/Live/Closing values.

## Schedule

- `production-generate.yml`: once after midnight Europe/Belgrade; generates Production picks and sends the email.
- `production-odds.yml`: every 5 minutes; the collector itself decides which fixtures are due, covering the next 72 hours.
- `production-settlement.yml`: every 15 minutes; settles finished Production bets.
- `pages.yml`: publishes the single Production dashboard.

## API budget

The provider's Pro plan is 7,500 requests/day. The system keeps an internal reserve and a global quota ledger. The 72h collector uses one odds request per fixture when that fixture is due; one response contains the whitelisted bookmakers for that fixture, so bookmaker count does not multiply the fixture request.

We will measure real daily usage before changing cadence. If the real universe cannot be covered inside 7,500 requests/day, the system must say so rather than silently dropping fixtures.

## Bookmakers

Production odds are hard-whitelisted to bookmaker IDs already defined by the model (`8`, `11`, `34`). The exact bookmaker returned by the API is retained with every observation. A later observation is never substituted from another bookmaker after Pick.

## Model

The existing mathematical model is frozen during this stabilization phase. No threshold, calibration, Dixon-Coles or staking changes are part of this reset.

## Second phase

Strong Signals will return later as an isolated analytical sector. Near Miss is not part of the Production dashboard or Production orchestration. Historical files are preserved.
