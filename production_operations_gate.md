# Production Operations Gate — Issue #58

Reviewed commit: `1875106a72cdadaa794a3394403a33ad4012eeea`
Workflow run: `QuantBet exhaustive odds capture` / `34423801954`

## Current persisted evidence
- Canonical snapshots: **4841**
- Distinct lifecycle keys: **3535**
- Snapshot types: `{'CLOSING': 13, 'ENTRY': 1868, 'INTERMEDIATE': 1296, 'OPENING': 1664}`
- Opening keys: **1664**
- Entry keys: **1868**
- Closing keys: **13**
- Collection outcomes: `{'INVALID_RESPONSE': 12, 'NO_ODDS_RESPONSE': 101, 'QUERIED': 278}`
- Eligibility reasons: `{'ELIGIBLE': 391, 'EXPLICIT_EXCLUSION': 312, 'INELIGIBLE_COUNTRY': 62, 'UNKNOWN_LEAGUE_TIER': 1450}`
- Persisted fixture states with an outcome field: **391**

## API budget
- Working budget: **7000**
- Used in current persisted budget ledger: **395**
- Remaining working budget: **6605**
- Historical API usage by day: `{'2026-09-07': 839, '2026-09-08': 890, '2026-09-09': 141, '2026-09-10': 132}`

## Operational invariants
- PASS — budget_within_working_limit
- PASS — no_post_kickoff_closing
- PASS — malformed_snapshot_rows
- PASS — coverage_has_explicit_outcomes
- PASS — eligibility_has_explicit_reasons
- PASS — state_has_fixture_outcomes

## Lifecycle integrity
The collector must only create OPENING from the first real pre-entry observation, retain exact ENTRY linkage from production generation, and use only T-5/CLOSING observations before kickoff for Closing. Missing stages are reported as collection outcomes rather than fabricated.

## Real-run evidence policy
Scheduled workflow execution is considered evidence only when its fixture-level state, coverage ledger, API budget ledger and immutable observation store are persisted. A green workflow alone is not treated as proof of collection completeness.

## Combined Football API accounting
All Football workflows use the same provider quota and the repository-wide `quantbet-ledger` concurrency group for canonical ledger writers. Per-workflow request counts remain attributable through API usage telemetry; the exhaustive collector additionally enforces its own working budget plus reserve. The gate does not treat separate workflow budgets as independent provider quotas.

## Decision
PASS — operational evidence is persisted and guarded by automated invariants. The gate intentionally does not modify model, calibration, EV, edge, Kelly, risk, strategy thresholds or CLV mathematics.
