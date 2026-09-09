# Issue 66 — GitHub Pages delivery forensic audit

## Reviewed state

- Repository: `Filip1994/h2h`
- Reviewed `main` SHA: `6ddb9f617cd3e7f5d288a2e73643fc2b54f4efe6`
- Reviewed at: 2026-09-09
- Public-data sources reviewed: `bets.json`, `ledger_meta.json`, `strong_signals.json`, `near_misses.json`, `intraday_alerts.json`, dashboard HTML/JS, and Pages workflow.

`main` is not empty. `bets.json` contains current Production history and `ledger_meta.json` contains current paper-ledger metadata. The reviewed `ledger_meta.json` reports `updated_at=2026-09-09T07:08:08.421056+02:00` and `data_cutoff=2026-09-09T05:08:08.421056+00:00`.

The latest reviewed `main` commit (`6ddb9f6`) is a GitHub Actions settlement/ledger commit at `2026-09-09T05:22:01Z`, proving that the canonical branch can move after the dashboard data was last generated.

## Data path audit

| Layer | Evidence | Result |
|---|---|---|
| Canonical source | `bets.json`, `ledger_meta.json` on `main` | PASS — non-empty/current data exists |
| Pages checkout | `pages.yml` explicitly checks out `main` | PASS — intended source is `main` |
| Artifact inputs | `pages.yml` copies `bets.json` and `ledger_meta.json` into `_site` | PASS |
| Artifact validation | workflow checks files are non-empty and parses JSON | PASS |
| Browser fetch contract | `qb-dashboard.js` fetches `./bets.json` and `./ledger_meta.json` with a cache-busting query string | PASS |
| History independence | History is built from `bets.json` plus optional Strong/Near datasets | PASS — it does not require today's active signal count |
| Optional datasets | Strong/Near/alerts are loaded through a failure-safe optional loader | PASS — missing optional files do not abort History |
| Deployment freshness | no immutable public deployment manifest existed | GAP — a stale Pages artifact could not be proven from the deployed surface alone |

## Proven root cause

The primary synchronization defect is **Pages trigger coverage**, not the History renderer.

The original `pages.yml` listened to `workflow_run` completion for the main data producers, but **did not include `QuantBet CLV persistence`**. That workflow writes the canonical `bets.json`, `predictions.json`, and `data/odds_snapshots.jsonl` and then pushes them to `main`. Because that push is performed with `GITHUB_TOKEN`, it must not be relied on to recursively start another workflow. Therefore a successful CLV-persistence commit could leave Pages serving the previous artifact until the hourly safety schedule fired.

The original Pages job also had:

```yaml
if: ${{ github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success' }}
```

This made a `workflow_run` event for a failed/cancelled/skipped producer create a Pages workflow whose deployment job was skipped. That is safe for not publishing failed output, but it is unsafe as a delivery architecture when `main` already contains the last canonical state and the public site needs to catch up to it. The result is a false coupling between producer conclusion and public deployment.

The issue report's observed `workflow_run` → `skipped` Pages behavior is consistent with this condition.

## Trigger matrix — reviewed architecture

| Producer | Mutates public data | Pages trigger before fix | Failure mode before fix |
|---|---:|---:|---|
| Daily QuantBet bulletin | Yes (`bets.json`, `ledger_meta.json`, health) | Yes | None when successful; GITHUB_TOKEN push was covered only indirectly |
| Intraday strong-signal scanner | Yes (`bets.json`, alerts/health) | Yes | Same indirect push limitation |
| Adaptive watchlist monitor | Yes (`strong_signals.json`, `near_misses.json`, observations) | Yes | Same indirect push limitation |
| Monitor odds and settle ledgers | Yes (`bets.json`, predictions) | Yes | Same indirect push limitation |
| T-5 closing odds capture | Yes (`bets.json`, `strong_signals.json`) | Yes | Same indirect push limitation |
| **CLV persistence** | **Yes (`bets.json`, `data/odds_snapshots.jsonl`)** | **No** | **Confirmed delivery gap; public Pages could remain behind `main` until hourly deploy** |
| Closing-day bulletin | Yes / potentially public ledger | Yes | Same indirect push limitation |
| Skip pending bet | Yes (`bets.json`) | Yes | Same indirect push limitation |

`QuantBet settlement watchdog` was reviewed and does not directly mutate the public data; it triggers/recoveries the existing monitor workflow, so it is not a separate Pages producer.

## Frontend/runtime audit

`assets/qb-dashboard.js`:

- fetches `bets.json` and `ledger_meta.json` as required inputs;
- fetches Strong/Near/odds state as optional inputs;
- catches top-level fetch/JSON failures and exposes `ERROR` rather than rendering a healthy blank dashboard;
- renders History from Production + Strong + Near datasets;
- does not require an active signal to render historical Production records;
- uses `?v=Date.now()` and `cache: no-store` for data fetches;
- does not have a service-worker dependency.

Therefore the first proven divergence is **deployment synchronization**, not a History predicate that discards valid Production history.

## Repair

1. Add `QuantBet CLV persistence` to the Pages `workflow_run` producer list.
2. Remove the success-only deployment gate. Pages now deploys the current canonical `main` state for every completed producer event; producer failure/cancellation/skipping is not treated as proof that the deployed data is healthy.
3. Preserve the hourly schedule as a safety reconciliation path.
4. Publish a `deployment_meta.json` manifest containing:
   - exact checked-out `main` SHA;
   - deployment build timestamp;
   - upstream workflow name/run ID/conclusion when available;
   - SHA-256 and byte length for canonical public JSON inputs.
5. Publish operational health files when present so the public artifact contains the evidence needed to distinguish stale/degraded data from an empty signal set.
6. Add regression tests for producer coverage, no success-only workflow gate, artifact manifest generation, and the hourly safety deploy.

## Scope guardrails

No changes were made to:

- model mathematics;
- calibration;
- probabilities;
- EV/edge;
- Kelly/staking/risk;
- eligibility;
- odds collection cadence;
- settlement mathematics;
- CLV mathematics;
- H2H;
- Production accounting.

## Remaining verification gate

The repaired branch must be merged and the resulting Pages deployment must be observed on the post-merge `main` state. The final verification must prove:

`post-fix main SHA → Pages workflow → Pages artifact → public deployment`

and compare the published `deployment_meta.json`, `bets.json`, and `ledger_meta.json` with the same `main` commit.
