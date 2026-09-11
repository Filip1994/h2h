# QuantBet Football v2

Production-only **paper-trading** football market screening system.

## Production decision path

`fixture discovery → eligibility → Dixon–Coles fit → market probabilities → odds/de-vig → EV/edge → risk allocation → Production ledger → Opening/Pick/Closing → settlement/CLV`

Production uses:

- API-Football for fixtures and odds;
- deterministic football eligibility;
- Dixon–Coles score modelling;
- same-bookmaker paired-market de-vig;
- EV/edge gates;
- capped fractional Kelly and exposure/drawdown controls;
- immutable odds observations and lifecycle provenance;
- settlement and CLV persistence;
- Gmail bulletin delivery;
- a static GitHub Pages dashboard.

**Strong Signals, Near Misses, market-timing/watchlist systems, H2H research artifacts and backtesting are not part of the current runtime.** They are intentionally excluded until Production is operationally reliable.

`PAPER_MODE=true` is the safe default.

## Runtime workflows

| Workflow | Purpose |
|---|---|
| `production-generate.yml` | Daily Production generation and bulletin |
| `production-odds.yml` | 5-minute odds collection, T-15 closing capture and dashboard deployment |
| `production-odds-watchdog.yml` | Self-healing recovery when the odds collector misses its heartbeat |
| `production-settlement.yml` | Production settlement |
| `pages.yml` | Static Pages recovery/reconciliation |
| `tests.yml` | Automated test suite |
| `skip.yml` | Owner-authorized manual Production skip requests |

The odds collector intentionally runs at minute `3/5` rather than minute `0/5` to reduce exposure to GitHub Actions top-of-hour scheduling congestion. The watchdog runs offset from it and can dispatch a recovery run when the latest collector heartbeat is older than the configured threshold.

## Dashboard

The dashboard is intentionally **read-only/static**. It consumes the committed `production_dashboard.json` and `production_quote_health.json` artifacts.

The browser fetches JSON with cache-bypass semantics and periodically reloads the page so a long-running tab does not remain stale.

## Production odds lifecycle

Canonical lifecycle:

`Opening → Pick → Closing → CLV`

- **Opening** = earliest valid pre-Pick quote for the exact lifecycle identity.
- **Pick** = exact decision-entry observation.
- **Closing** = exact-bookmaker pre-kickoff observation resolved around T-15.
- Missing stages remain unavailable; there is no bookmaker substitution or Pick-as-Opening fallback.

The collector also has a narrow late T-15 recovery window so a delayed GitHub scheduler run can still capture a valid pre-kickoff closing observation.

## Supported production markets

- `OVER_2_5`
- `UNDER_2_5`
- `BTTS_YES`

There is no artificial fixed daily pick count. Independently qualifying markets enter the risk allocator subject to exposure, drawdown and circuit-breaker controls.

## Risk defaults

- quarter Kelly;
- maximum 1% bankroll per bet;
- maximum 3% new daily exposure;
- maximum 5% total open exposure;
- configurable stake minimum/step;
- stakes halved at 5% current drawdown;
- new positions stopped at 10% current drawdown.

These limits are configuration controls, not evidence of profitability.

## Configuration

Repository secrets:

- `API_FOOTBALL_KEY`
- `GMAIL_USER`
- `GMAIL_APP_PASS`
- `EMAIL_TO` (optional; defaults to `GMAIL_USER`)

Repository variable:

- `PAPER_MODE=true`

## Local verification

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff format --check .
ruff check .
pytest
cp .env.example .env
python main.py analytics
```

Useful production commands:

```bash
python main.py generate
python main.py generate --no-email
python main.py capture-odds
python main.py monitor
python main.py calibrate
python main.py analytics
python main.py skip --id 1590051_UNDER_2_5
```

## Operating posture

Production remains in paper mode until operational reliability and genuine out-of-sample evidence are established. A green dashboard or small ROI sample is not sufficient evidence for live trading.
