# QuantBet H2H v2

Launch-ready **paper-trading** architecture for football market screening. The engine combines:

- API-Football as the data and odds feeder;
- a fitted Dixon–Coles score model;
- strict, time-decayed H2H eligibility rules;
- paired-market de-vig and expected-value gates;
- capped fractional Kelly and portfolio drawdown limits;
- Gmail delivery, GitHub Pages dashboard and auditable JSON ledgers.

`PAPER_MODE=true` is the safe default. The code refuses uncalibrated live mode unless that guard is explicitly bypassed.

## 1. Replace the old architecture

Use this project as the repository root. Remove the old `value_engine.py`, `market_drop_engine.py` and `quant_math.py`; their responsibilities are now separated under `src/quantbot/`.

Preserve the existing `bets.json` before replacing files. Legacy market names are supported by settlement, and every existing `PENDING`, `WIN`, `LOSS` or `SKIPPED` fixture remains blocked from future bulletins.

The supplied ledger preserves the five uploaded `PENDING` bets. Their open stake is 5,000 RSD, above the new 5% cap for a 50,000 RSD bank, so new allocation is intentionally frozen until exposure falls through settlement or an authorized skip.

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

Environment variables are read directly by the process. Load `.env` with your preferred local mechanism; the application deliberately does not add another dependency for it.

## 3. GitHub configuration

Repository secrets:

- `API_FOOTBALL_KEY`
- `GMAIL_USER`
- `GMAIL_APP_PASS`
- `EMAIL_TO` — optional; defaults to `GMAIL_USER`

Repository variable:

- `PAPER_MODE=true`

In **Settings → Pages**, select **GitHub Actions** as the publishing source. `pages.yml` deploys only `index.html`, `bets.json` and `ledger_meta.json`; secrets, source code and calibration data are not published. Relative reads keep forks and renamed repositories working.

Workflow permissions must allow GitHub Actions to write repository contents. The workflows use explicit `contents: write`, serialize all ledger mutations through one concurrency group, and never embed API or Gmail credentials in files.

The API client uses atomic TTL caching, a hard per-run request budget and at most three bounded exponential-backoff attempts for HTTP `429`/`5xx` or transient network failures.

## 4. Workflows

| Workflow | Schedule | Function |
|---|---:|---|
| `daily.yml` | 06:00 UTC daily | Generate, commit, then email bulletin |
| `monitor.yml` | Every 30 minutes | Capture last available pre-kickoff quote and settle ledgers |
| `calibrate.yml` | Sunday 05:30 UTC | Refit per-market Platt calibration |
| `skip.yml` | Authorized GitHub Issue opened | Exact ID transition `PENDING → SKIPPED` |
| `pages.yml` | State change + hourly fallback | Deploy the current dashboard artifact |
| `tests.yml` | Push/PR | Run the regression suite |

GitHub schedules are UTC and can be delayed by platform load. Match display uses `Europe/Belgrade`, including daylight-saving transitions. State-writing workflows always check out the latest default branch and serialize mutations. They explicitly dispatch `pages.yml` after their commit because bot-authored commits do not trigger another ordinary workflow run. Skip issues are accepted only from an owner, organization member or repository collaborator.

## 5. Commands

```bash
python main.py generate             # generate + email
python main.py generate --no-email  # two-phase GitHub workflow
python main.py send-report
python main.py monitor
python main.py skip --id 1590051_UNDER_2_5
python main.py calibrate
python main.py analytics
```

## 6. Selection contract

A fixture is considered only when all conditions hold:

1. Senior/professional league and teams pass the league + both-team exclusion check.
2. Fixture does not already exist in `bets.json` under a blocking status.
3. At least five valid H2H matches fall inside the exact rolling four-year window.
4. At least one H2H match is newer than 730 days.
5. A market's time-decayed H2H hit rate is at least 75%.
6. Dixon–Coles training has enough league and team history.
7. Both sides from one bookmaker exist and market overround is between 0% and 20%, permitting a credible de-vig.
8. Offered decimal odds are at least 1.45.
9. Conservative probability passes both `EV >= 5%` and edge `>= 3 percentage points`.
10. Portfolio and drawdown budgets permit the stake.

At most one market is selected per fixture. The three supported markets are `OVER_2_5`, `UNDER_2_5` and `BTTS_YES`. Goals in both halves remain excluded because a full-time Dixon–Coles model cannot price the two half-specific intensities rigorously.

## 7. Risk defaults

- quarter Kelly;
- maximum 1% bankroll per bet;
- maximum 3% new daily exposure;
- maximum 5% total open exposure;
- stake step 50 RSD and minimum stake 100 RSD;
- stakes halved at 5% current drawdown;
- new positions stopped at 10% current drawdown.

These are environment-configurable limits, not evidence that the strategy has positive expected return.

## 8. Calibration and live-mode guard

`predictions.json` records every modelled market in the H2H-qualified fixture universe, including unselected predictions. Settlement supplies binary outcomes. Weekly calibration uses a chronological 70/30 split. Platt scaling is accepted only if both Brier score and log-loss do not worsen on the held-out 30%; the selected Platt or identity mapping is valid only when held-out 10-bin ECE is at most 5%.

By default, each market needs at least 200 settled out-of-sample predictions. Until all three markets validate, `PAPER_MODE=false` is rejected unless `ALLOW_UNCALIBRATED_LIVE=true`. Do not use that bypass for real staking.

## 9. Historical walk-forward backtest

Populate `data/backtest_template.csv`, then run:

```bash
python backtest.py --input data/history.csv
```

The backtest trains only on earlier dates, predicts a full day before adding that day's outcomes, periodically refits the model, applies the H2H and EV contracts, reports Brier/log-loss, per-market ROI, drawdown, losing streak and a deterministic day-cluster bootstrap 95% ROI interval, and writes a candidate `calibration.json`. The interval is withheld until at least 30 independent matchdays exist. Selection ROI uses raw out-of-sample probabilities minus the configured haircut; the candidate calibration is fitted afterward and is never retroactively applied to those same selections.

Historical odds must represent prices genuinely available at the decision timestamp. Closing or retrospectively selected best prices create leakage and invalidate ROI.

Each CSV row containing odds must also contain `bookmaker_id` and an ISO-8601 `odds_captured_at` strictly earlier than fixture `date`. All paired prices in that row must come from that bookmaker snapshot; the backtest fails instead of reporting ROI when timestamp proof is absent or post-kickoff.

## 10. Launch sequence

1. Preserve the current ledger and push this code on a review branch.
2. Run `tests.yml`.
3. Add secrets and keep `PAPER_MODE=true`.
4. Manually dispatch `daily.yml`; verify email, API usage and `bets.json` commit.
5. Manually dispatch `monitor.yml`; verify quote snapshots and settlement.
6. Set Pages source to **GitHub Actions**, dispatch `pages.yml`, and inspect mobile rendering.
7. Accumulate or import valid out-of-sample predictions.
8. Review calibration, CLV, drawdown and the day-cluster ROI interval; do not consider live mode while its lower 95% bound is non-positive.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the mathematical contract.
