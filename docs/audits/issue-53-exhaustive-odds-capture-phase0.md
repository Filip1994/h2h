# Issue #53 — Phase 0 exhaustive odds capture audit

Audit baseline: `main` at `191029fc29fb800d4ff52246468182a9fbfdaa84`.

## 1. API budget and actual recent usage

Configured defaults in `Settings` are:

- API request budget: **7,500**
- protected reserve: **500**
- working budget: **7,000**

The committed `api_usage_history.json` shows substantial under-utilisation:

| Business date | Requests | Odds requests | Fixture requests | Working budget | Utilisation |
|---|---:|---:|---:|---:|---:|
| 2026-09-07 | 839 | 198 | 608 | 7,000 | 12.0% |
| 2026-09-08 | 890 | 191 | 397 | 7,000 | 12.7% |

No rate-limit, HTTP or network errors were recorded in the retained 2026-09-08 samples. The dominant failure mode is therefore **missing collection coverage, not API exhaustion**.

## 2. Fixture-universe coverage

The existing generation ledger does not persist a complete daily eligible Football fixture universe or an auditable per-fixture odds-query outcome. Therefore `queried / eligible` cannot honestly be reconstructed from the current committed state.

This is a concrete observability defect. The new collector must persist every eligible fixture and an explicit outcome (`QUERIED`, `NO_ODDS_RESPONSE`, `API_ERROR`, `BUDGET_EXHAUSTED`, `INELIGIBLE`, etc.).

## 3. Existing odds observation ledger

`data/odds_snapshots.jsonl` exists and is canonical for signalised lifecycle observations, but it is not a fixture-universe collection ledger. It therefore cannot prove that fixtures without a signal were queried.

The existing lifecycle model already supports `OPENING`, `ENTRY`, `INTERMEDIATE`, `T5`, and `CLOSING`. The remaining gap is upstream: **collecting repeated real observations before a fixture becomes a prediction/bet**.

## 4. Production / Strong Signal coverage

Production records contain some entry/closing fields, but there is no first-class fixture-level coverage record tying every eligible fixture to the observation cadence.

Strong Signal records use the same odds concepts, but their observation coverage is likewise not independently auditable from the committed public signal ledgers.

No historical value should be fabricated to make the coverage percentages look better.

## 5. Workflow execution

The existing adaptive watchlist runs every two minutes during the configured daytime window, but it is still **signal-led**. It is not an exhaustive fixture-universe odds collector.

A successful workflow execution therefore cannot be interpreted as successful odds coverage. The new collector must persist actual scan timestamps and per-fixture outcomes.

## 6. Provider availability by time-to-kickoff

The current committed data does not preserve enough fixture-universe state to measure provider odds availability cleanly at T-72h, T-48h, T-24h, T-12h, T-6h and nearer kickoff across all eligible fixtures.

The implementation will explicitly record provider-empty responses, so lack of odds is distinguishable from lack of querying.

## 7. Phase 0 conclusion

**PASS — implementation may proceed.**

The audit proves two important facts:

1. available API capacity is materially under-used (roughly 12–13% of the working budget in the latest two business dates); and
2. the primary lifecycle gap is upstream collection/observability, not the public UI or lifecycle selector itself.

This phase changes no model, EV, edge, Kelly, risk, eligibility, Strong Signal threshold, or betting-strategy mathematics.
