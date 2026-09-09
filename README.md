# QuantBet Football v2

Launch-ready **paper-trading** architecture for football market screening. The current Production decision path uses:

- API-Football as the data and odds feeder;
- a fitted Dixon–Coles score model;
- deterministic Football league/competition eligibility;
- paired-market de-vig and expected-value gates;
- capped fractional Kelly and portfolio drawdown limits;
- canonical odds lifecycle, settlement and CLV persistence;
- Gmail delivery, GitHub Pages dashboard and auditable JSON ledgers.

**H2H is not part of the current Production decision path.** Historical H2H datasets and documentation may remain for research/provenance, but they do not determine Production eligibility, probability, EV, edge, stake or fixture selection.

`PAPER_MODE=true` is the safe default.

## 1. Current architecture

Production flow is:

`fixture discovery → eligibility → Dixon–Coles fit → market probabilities → odds/de-vig → EV/edge → risk allocation → Production ledger → Opening/Pick/Closing → settlement/CLV`

Production, Strong Signals and Near Misses share compatible canonical observation/lifecycle data but remain separate accounting/presentation surfaces. Strong Signals are virtual/counterfactual and do not change Production P/L or bankroll.

Historical H2H artifacts are retained only as historical/research provenance and are not required for the current Production runtime.

## 2. Local verification

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

## 3. GitHub configuration

Repository secrets:

- `API_FOOTBALL_KEY`
- `GMAIL_USER`
- `GMAIL_APP_PASS`
- `EMAIL_TO` — optional; defaults to `GMAIL_USER`

Repository variable:

- `PAPER_MODE=true`

GitHub Pages publishes only the intended public dashboard/data artifacts. Secrets, source code and calibration data are not published.

Football API requests are governed by the global quota mechanism and workflow serialization. The API client uses atomic TTL caching and bounded retries for transient failures.

## 4. Core workflows

| Workflow | Function |
|---|---|
| `daily.yml` | Scheduled Production generation and bulletin delivery |
| `odds-capture.yml` | Exhaustive eligible-football odds observation |
| `intraday.yml` | Scheduled Production/Strong/Near scanning |
| `watchlist.yml` | Strong/Near market observation and lifecycle persistence |
| `monitor.yml` | Settlement and lifecycle monitoring |
| `closing-capture.yml` | Canonical closing observation capture |
| `clv-persistence.yml` | Opening/Pick/Closing/CLV persistence |
| `pages.yml` | Public dashboard deployment |
| `calibrate.yml` | Chronological calibration evaluation |

Schedules use GitHub Actions cron semantics; public timestamps are interpreted/displayed in `Europe/Belgrade`.

## 5. Commands

```bash
python main.py generate
python main.py generate --no-email
python main.py send-report
python main.py monitor
python main.py skip --id 1590051_UNDER_2_5
python main.py calibrate
python main.py analytics
```

## 6. Production decision contract

A fixture must pass the central Football eligibility gate, have sufficient Dixon–Coles training data, valid supported market odds, valid same-bookmaker paired odds for de-vig, minimum odds and the configured EV/edge strategy gates, and available portfolio risk capacity.

The current supported production markets are `OVER_2_5`, `UNDER_2_5` and `BTTS_YES`; these machine codes are rendered as canonical human-readable labels in public presentation.

There is no artificial fixed daily Production pick count. Independently qualifying markets reach the risk allocator; risk, exposure, drawdown and circuit-breaker controls remain authoritative.

## 7. Risk defaults

- quarter Kelly;
- maximum 1% bankroll per bet;
- maximum 3% new daily exposure;
- maximum 5% total open exposure;
- configured stake step/minimum;
- stakes halved at 5% current drawdown;
- new positions stopped at 10% current drawdown.

These are environment-configurable limits and are not evidence that the strategy has positive expected return.

## 8. Calibration and live-mode guard

`predictions.json` records modelled markets for out-of-sample calibration. Weekly calibration uses a chronological split and requires the configured validation sample and calibration-quality criteria before being marked valid.

Until all required markets validate, live mode remains blocked by default. Calibration validity alone is not evidence of profitability; CLV, uncertainty and out-of-sample performance must also be reviewed.

## 9. Odds lifecycle and provenance

The canonical lifecycle is:

`Opening → Pick → Closing → CLV`

Opening is the earliest valid observed pre-Pick quote for the exact lifecycle identity. Pick is the exact decision-entry observation. Closing is the canonical valid pre-kickoff closing observation. Missing stages remain explicitly unavailable; no Pick-as-Opening or bookmaker substitution is allowed.

Every Production Pick carries immutable decision provenance sufficient to reconstruct its decision context, subject to the availability of referenced source observations.

## 10. Research boundary

Research work may evaluate Model V2, drift, signal strength, market-vs-model benchmarks and timing intelligence, but research changes must not silently alter Production. Promotion requires the explicit research-to-production gate.

Historical H2H data is research/provenance only and is not a Production feature.

## 11. Operating posture

Keep Production in paper mode while the operational readiness gate and genuine out-of-sample evidence accumulate. Do not infer readiness from a green UI or a small ROI sample.

See `ARCHITECTURE.md` for the mathematical and runtime contract.
