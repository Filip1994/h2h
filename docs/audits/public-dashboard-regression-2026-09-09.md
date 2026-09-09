# Public Dashboard Regression Audit — 2026-09-09

## Scope
Audit the latest scheduled/publication state after commit `68915e6d8232e9d3984de71819fd19f3fdf77e56` (`Update QuantBet signal classification observations`).

## Findings

### 1. Pages deployment itself is green
The GitHub Pages deployment for `68915e6d8232e9d3984de71819fd19f3fdf77e56` completed successfully. This proves deployment/build execution, not functional correctness of the public dashboard.

### 2. The immediately preceding scheduled state is also operational
The settlement watchdog scheduled run completed successfully, including the settlement-health check. The scheduled Strong Signal watchlist job also completed successfully, including isolated public dataset build, publication-contract validation, and commit.

### 3. Latest public-data commit is narrowly scoped but high-risk for dashboard contracts
The latest commit modifies only generated/data state:
- `data/intraday_signal_events.jsonl`
- `data/market_timing_snapshots.jsonl`
- `data/raw_api/2026-09-09.jsonl`
- `intraday_watchlist_state.json`
- `market_timing_metrics.json`
- `near_misses.json`

It does not modify frontend source in this commit. Therefore a visible dashboard regression is most likely a **data/schema/public-contract regression or generated-state incompatibility**, not a Pages build failure.

### 4. Important lifecycle evidence
The parent scheduled commit changed a historical intraday alert from `PENDING` to `SKIPPED` for an alert sent on 2026-09-08. This confirms that historical alert state is actively being rewritten by operational reconciliation. Such transitions must remain semantically valid and must not break public consumers.

## Required engineering investigation

1. Reproduce the reported dashboard break against the currently deployed `main` state.
2. Compare the latest public datasets with the last known-good deployed dataset state.
3. Validate every public JSON artifact against the frontend's actual runtime schema/contracts.
4. Verify that empty collections, missing optional fields, null lifecycle values, status transitions, and large historical collections remain valid inputs.
5. Verify that `near_misses.json` growth and `intraday_watchlist_state.json` rewrites cannot cause rendering failure, stale UI, malformed parsing, or unexpected memory/performance degradation.
6. Verify that automated jobs only mutate the public datasets they own and cannot overwrite incompatible state produced by another workflow.
7. Add an automated **functional public-dashboard contract test** that loads the generated datasets exactly as the frontend does and fails CI if the dashboard cannot render its required views.
8. Add regression coverage for historical status transitions such as `PENDING -> SKIPPED`, without deleting historical evidence or fabricating settlement.
9. Verify that a green Pages build is not considered sufficient evidence of dashboard health.
10. Run the resulting contract test against a real scheduled-generated dataset before closing the issue.

## Non-goals
- Do not rollback or delete history merely to restore the UI.
- Do not alter settlement mathematics.
- Do not alter Dixon-Coles/model mathematics, calibration, de-vig, EV/edge, Kelly, risk, eligibility, bookmaker policy, lifecycle semantics, or H2H.
- Do not silently filter away malformed historical records; classify and handle them explicitly.

## Definition of Done
The deployed dashboard renders correctly from the exact generated datasets produced by scheduled automation; all public views have validated contracts; historical records remain preserved; and a future generated-data/schema regression causes an explicit contract-test failure before publication.