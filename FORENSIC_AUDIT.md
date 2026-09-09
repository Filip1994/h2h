# QuantBet Forensic Audit — Issue Board + System

Date: 2026-09-09

## Executive conclusion

Do not rebuild the model from zero. The core Dixon-Coles/model/market/risk layer is reusable. The main failure mode was feature delivery outrunning orchestration, persistence, lifecycle and operational-proof maturity.

The reset is therefore an operational architecture reset: one canonical state authority, one serialized set of ledger writers, fail-closed health, and runtime evidence before issue closure.

## Issue-board classification

### GREEN — substantially implemented

#18, #19, #31/#32, #40, #48, #55, #63, #77, #79, #81.

These have concrete implementation/regression coverage and should only reopen on a new regression.

### AMBER — implementation exists; operational proof or completeness remains

#42/#46/#68 — settlement/lifecycle history.

#50/#58/#72/#73/#80 — lifecycle, public semantics and 72h odds capture.

#57 — centralized fail-closed eligibility exists, but global universe coverage remains a maintained registry requiring operational proof.

#75 — Strong Signal accounting separation exists; scheduled runtime proof remains.

#109/#112/#116 — observability/provenance refinements depend on the stabilization layer for trustworthy runtime proof.

### RED — system-critical open work

#78 global Football API quota; #83 decision funnel telemetry; #111 intraday runtime proof; #114 shared-state writer race; #117 provenance stale-write race; #59 final production readiness gate.

## Repeated failure patterns

1. Health was weaker than the dashboard contract. The old settlement check could report OK while malformed or not-yet-old PENDING records were still visible as Active.
2. Shared ledger writers did not all use the same concurrency boundary. Watchlist and manual SKIP used separate groups from settlement/generation/odds.
3. Atomic JSON writes plus Git retries were being used as a substitute for a canonical transaction/state authority.
4. Issues could be closed after code/tests without real scheduled-runtime proof.

## Canonical Production invariant

Every canonical record has a known state and stable id. Every active record has a valid event_id and kickoff. No active record may remain stale past the settlement threshold. Terminal results require settlement evidence except explicit SKIPPED semantics. Missing/invalid canonical data is FAIL, never OK. Dashboard deployment is blocked by unsafe canonical state.

## Closure protocol

incident -> root cause -> code fix -> regression test -> scheduled runtime proof -> public artifact proof -> CLOSED

## Stabilization delivered in PR #123

- Added `tools/system_health.py` as a fail-closed canonical state/settlement checker.
- Made `tools/settlement_health.py` delegate to the canonical checker.
- Unified watchlist and manual SKIP writers with the global Football concurrency group.
- Monitor now persists canonical `system_health.json` and fails on unsafe state.
- GitHub Pages refuses unsafe canonical state and publishes `system_health.json` with the dashboard artifact.
- Added regression tests for stale Active state, malformed kickoff, missing terminal settlement evidence and valid Active state.

## Deliberately not closed

This stabilization does not claim #78, #83, #111, #114, #117 or #59 are complete. They still require real scheduled-runtime evidence.

## Rebuild recommendation

Freeze model/strategy changes until the operational gate is green. Preserve the model layer; rebuild the orchestration/state/observability layer around it. Then resume feature work only through explicitly scoped research/model issues.
