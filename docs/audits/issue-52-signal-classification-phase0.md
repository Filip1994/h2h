# Strong Signal vs Near Miss — Phase 0 Forensic Audit

Generated from the current `main` repository state on 2026-09-09 before behavioral implementation.

## Executive conclusion

The current system **cannot honestly prove that today's Strong Signal count is zero** from persisted scan evidence. The public Strong Signals dataset contains historical Strong events, while the intended `data/market_timing_snapshots.jsonl` observation ledger is not present in the current `main` tree. The watchlist state shows scans through 2026-09-08, but it does not persist a first-class Near-Miss history or a complete scan funnel.

Therefore the correct audit conclusion is **UNPROVEN**, not "zero Strong Signals". This is itself a production observability defect addressed by Issue #52.

## A. Current classification contract — verified before changes

`src/quantbot/watchlist.py` currently has two separate predicates:

- Strong: `is_strong_signal()` requires EV >= `settings.strong_signal_min_ev`, probability edge >= `settings.strong_signal_min_edge`, and stake >= `settings.strong_signal_min_stake`.
- Near Miss: `_near_miss()` computes decision probability as calibrated probability minus the existing haircut, then classifies when EV >= `settings.min_ev - 0.03` **OR** edge >= `settings.min_edge - 0.02`.
- Observed: valid quote that is neither Strong nor Near Miss.

The code currently stores only `was_strong` and `last_seen_at` per prediction key, so transitions are not first-class historical events.

## B. Actual workflow roles

Verified workflow configuration:

| Workflow | Schedule | Role |
|---|---|---|
| `watchlist.yml` | `*/2 6-23 * * *` Europe/Belgrade | adaptive fixture odds observation and current Strong/Near-Miss calculation |
| `intraday.yml` | `*/30 6-23 * * *` Europe/Belgrade | generation/intraday scan and ledger/health persistence |

Watchlist uses a shared ledger concurrency group and an API request budget of 7,500 with a 500 request reserve. Intraday uses the same budget/reserve and concurrency group.

The workflow schedule alone is not proof of fixture coverage.

## C. Persisted evidence on `main`

- `generation_health.json` latest record: 2026-09-08 20:00 UTC, `HEALTHY`, 4 API requests, 1 fixture request and 3 odds requests, 0 new bets.
- `generation_health_history.json`: 3 retained records on 2026-09-08; two were `DEGRADED` because of fixture/Dixon-Coles processing failures and one was `HEALTHY`.
- `intraday_watchlist_state.json`: scan state exists through 2026-09-08, with adaptive cadences from 300s to 3600s. It contains `was_strong` booleans but no immutable class-event history.
- `strong_signals.json`: contains historical virtual Strong Signal records from 2026-09-07 and 2026-09-08. Examples include Estoril vs Arouca, Nueva Chicago vs Quilmes, AD Carmelita vs Pitbulls Santa Barbara FC, Al Mesaimeer vs Al Kharaitiyat, Lahti vs Mariehamn and Young Africans vs Geita Gold.
- `data/market_timing_snapshots.jsonl`: **not present in the audited `main` tree**. Consequently a complete persisted observation funnel cannot currently be reconstructed for 2026-09-09 or earlier dates from this file.

## D. Concrete classification/persistence defect

`watchlist.py` computes `near_miss` and `signal_state`, but its durable state only retains `was_strong` for a prediction key. The public builder `tools/build_public_strong_signals.py` merges prior public records, alerts and intraday bets into `strong_signals.json`; it does not build a separate canonical Near-Miss history.

This means a Near Miss can be observed transiently without becoming a first-class public historical event. A later Strong state can overwrite the observational distinction instead of preserving `NEAR_MISS → STRONG`.

## E. Why a zero-Strong day is currently unprovable

The latest persisted scan state is from 2026-09-08. There is no persisted market-timing observation ledger in `main` from which the 2026-09-09 funnel could be counted. Therefore:

- "Strong Signals = 0 today" is **not proven**;
- "Strong Signals > 0 today" is also **not proven**;
- dashboard emptiness must not be used as evidence either way.

Issue #52 must make this distinction machine-readable and auditable.

## F. Odds/validation integrity

The existing watchlist path requires a real quote returned by `extract_best_quotes()`, then rejects a market when no quote exists or when overround exceeds the configured maximum. API budget/API errors are caught and logged. No numeric default should create a signal in this path.

The audit does identify a telemetry gap: quote rejection reasons are not persisted as first-class funnel events, so a missing Near Miss/Strong classification cannot always be attributed to `NO_ODDS` vs validation vs API failure after the run.

## G. Public-output gap

Current `strong_signals.json` is Strong-focused and contains no first-class Near-Miss bucket. The public Strong Signals page therefore cannot demonstrate that a day with no Strong events contained Near Misses or only Observed quotes.

The public history also inherits machine market values in historical data; the canonical presentation layer from Issue #50 can translate these, but Issue #52 must attach the explicit signal class separately from market naming.

## H. Required repair direction

1. Introduce one canonical classification function preserving the verified existing threshold semantics.
2. Persist `STRONG_SIGNAL`, `NEAR_MISS`, and `OBSERVED` on every valid market-timing observation.
3. Persist immutable state-transition events so `NEAR_MISS → STRONG` is reproducible.
4. Create separate `strong_signals.json` and `near_misses.json` public buckets.
5. Ensure Near Misses never enter Production accounting or P&L.
6. Add a deterministic audit command that reports the scan funnel from persisted evidence for today and recent dates.
7. Persist reason-coded Near Miss classifications where the values support them.
8. Keep Issue #50's canonical odds lifecycle as the single odds observation stream.

## Phase 0 gate

**PASS — audit completed before behavioral implementation.**

No thresholds, model mathematics, eligibility, staking, Production accounting, or betting rules were changed by this audit.
