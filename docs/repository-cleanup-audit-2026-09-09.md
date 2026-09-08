# Repository cleanup audit — 2026-09-09

Scope: issue #40. Production behavior is intentionally unchanged.

## Branch audit

Branches with `ahead_by=0` have no commits unique to the branch relative to `main` and are confirmed obsolete candidates. Diverged branches with `ahead_by>0` are retained for review rather than deleted blindly.

### Confirmed obsolete candidates

- `backup/pre-v2.1` — ahead 0, behind 223
- `chore/daily-bulletin-0015` — ahead 0, behind 197
- `chore/daily-bulletin-0051` — ahead 0, behind 188
- `control-tower-generation-health-2026-09-08` — ahead 0, behind 51
- `feat/dashboard-football-baseball` — ahead 0, behind 186
- `feat/dashboard-football-baseball-v2` — ahead 0, behind 184
- `feat/decision-audit-retention` — ahead 0, behind 147
- `feat/futuristic-email-bulletin` — ahead 0, behind 170
- `feat/h2h-research-dataset-v1` — ahead 0, behind 77
- `feat/h2h-research-dataset-v1b` — ahead 0, behind 58
- `feat/intraday-signal-scanner` — ahead 0, behind 165
- `feat/signal-lifecycle-v2` — ahead 0, behind 106
- `fix/ci-format-main` — ahead 0, behind 156
- `fix/restore-dashboard-deploy` — ahead 0, behind 163
- `p1-generation-health-current` — ahead 0, behind 58
- `p1/generation-health-telemetry` — ahead 0, behind 3
- `p1-quantbet-takeover-2026-09-08` — ahead 0, behind 52
- `p2/fix-dashboard-freshness-age` — ahead 0, behind 12
- `v2.1.0-hardening` — ahead 0, behind 211

### Diverged — do not delete blindly

- `chore/disable-intraday-signal-emails` — ahead 1; workflow change
- `data-archive-observation` — ahead 11; API/raw-data changes
- `feat/clean-signal-lifecycle` — ahead 30; alert lifecycle/decision-audit work
- `feat/clv-persistence-linkage` — ahead 30; CLV persistence work
- `feat/h2h-research-dataset-v1b2` — ahead 24; H2H research work
- `feat/intraday-signal-scanner-watchlist` — ahead 20; scanner/watchlist work
- `feat/38-generation-health-funnel` — ahead 6; superseded by merged PR #39, but still unique commits
- `fix/h2h-enabled-propagation` — ahead 2; H2H test/code changes
- `fix/h2h-telemetry-install` — ahead 1; H2H workflow change
- `fix-canonical-closing` — ahead 25; closing/CLV work
- `fix-canonical-closing-current` — ahead 3; closing/CLV tests/work
- `p1-daily-delivery-current` — ahead 2; daily workflow/tests
- `p1-daily-delivery-hardening` — ahead 7; daily/settlement hardening
- `p1-generation-health-telemetry` — ahead 5; pre-#39 generation-health work
- `p1-h2h-telemetry-ledger` — ahead 13; H2H telemetry-ledger work
- `p1/finalize-h2h-removal` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-final` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-final2` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-final3` — ahead 17; full H2H-removal change set
- `p1/h2h-removal-v2` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-v3` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-v4` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-v5` — ahead 1; obsolete H2H-removal workflow
- `p1/h2h-removal-v6` — ahead 1; obsolete H2H-removal workflow
- `p1/tier1-tier2-production-eligibility` — ahead 16; eligibility changes
- `v2.2-api-intelligence` — ahead 18; API/engine/workflow changes

### Baseball

Baseball has moved to a separate repository. Therefore `baseball`, `feature/baseball-v1`, and `feature/baseball-live-v1` are deletion candidates from this repository and are outside the Football production boundary. They should be deleted as branch cleanup, not mixed into production code changes.

## File audit

- `.github/workflows/calibrate.ym` is byte-for-byte the same workflow as `.github/workflows/calibrate.yml` (same blob SHA `67c2a2...`). It is removed by this PR; the canonical `.yml` workflow remains.
- Runtime H2H modules `src/quantbot/h2h.py` and `src/quantbot/h2h_telemetry.py` are already absent from `main`.
- Remaining H2H references are research/history documentation and append-only research data; they are retained for provenance rather than removed blindly.
- Production ledgers and settlement/calibration artifacts are retained.

## Guardrails

No model, calibration, odds, EV, risk, settlement, cadence, league-eligibility, API strategy, or production behavior is changed by this cleanup.
