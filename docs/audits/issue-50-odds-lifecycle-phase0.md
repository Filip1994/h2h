# QuantBet Odds Lifecycle — Phase 0 Forensic Audit

Generated from the real `main` data set in CI on 2026-09-09.

## Executive conclusion

The audit proves that the provider archive is real and substantial, but the lifecycle is not yet complete or uniformly linked. The canonical odds ledger is populated (`2,468` records), while the raw archive contains `321` odds responses and `712,439` extracted quote rows. Production currently has `14` bets, of which `10` are only partially auditable and `4` have no matching archived odds for their exact fixture/market/bookmaker key.

The critical architectural defects are:

1. **Opening is not independent.** The current lifecycle derives ENTRY from the pick quote instead of selecting the earliest valid archived observation as Opening.
2. **Strong Signals and Production closing paths diverge.** Strong Signals uses T-5 fields in `intraday_alerts.json`, while Production closing/CLV uses the canonical bet/snapshot path.
3. **Lifecycle linkage is incomplete.** Existing CLV/lifecycle fields can exist without a complete auditable Opening/Pick/Closing chain.
4. **Bookmaker logos are not provider-sourced in the archive.** Provider bookmaker objects expose `id`, `name`, and `bets`, but no `logo` field. A deterministic verified registry is required if logos are to be shown.
5. **The scheduler is still in verification cadence.** `daily.yml` is `*/5 * * * *` and the watchdog is `2-59/5 * * * *`; recent scheduled runs observed in the Actions API include failures. Production cadence must not be declared restored until the actual Daily delivery path is proven and the temporary verification cadence is removed.

No product implementation changes were made before this audit report was produced. The audit tooling/workflow is audit-only infrastructure.

## A. Real source inventory

| Layer | Current evidence | Finding |
|---|---|---|
| API provider | API-Football `odds` endpoint in raw archive | Real source of bookmaker/market/selection/odd observations |
| Raw archive | `data/raw_api/*.jsonl` | 3 files, 99,856,164 bytes, 321 odds responses |
| Canonical snapshot ledger | `data/odds_snapshots.jsonl` | 2,468 records, 1,526,354 bytes |
| Production decisions | `bets.json` / `predictions.json` | 14 production bets audited |
| Strong Signals | `intraday_alerts.json` | Separate virtual/counterfactual signal state with separate T-5 fields |
| Closing | closing capture + persistence workflows | Separate capture/persistence boundary |
| Public UI | `index.html`, `strong-signals.html` | Must consume one canonical lifecycle contract |

Canonical snapshot types currently observed: `ENTRY=1666`, `INTERMEDIATE=792`, `CLOSING=10`.

Snapshot linkage counts observed: `prediction_id=2465`, `signal_id=2465`, `bet_id=20`.

## B. Provider schema — proven from real archived responses

The actual archived `odds` response shape is:

- response object keys: `bookmakers`, `fixture`, `league`, `update`
- fixture keys: `date`, `id`, `timestamp`, `timezone`
- league keys: `country`, `flag`, `id`, `logo`, `name`, `season`
- bookmaker keys: `bets`, `id`, `name`
- market keys: `id`, `name`, `values`
- selection keys: `odd`, `value`

Important conclusion: the audited provider bookmaker object does **not** contain a bookmaker logo field. The provider archive therefore cannot be used as proof of a bookmaker logo. The implementation must not invent a URL from the bookmaker name.

The provider does expose a fixture date/timestamp and the market/selection/odd itself, so repeated captures can reconstruct historical Opening only when our own archive contains an earlier valid observation for the exact lifecycle key.

## C. Actual capture timing

Across the 321 archived odds responses with a usable fixture kickoff timestamp:

- `GT6H`: 59
- `T3_6H`: 95
- `T1_3H`: 99
- `T30_60M`: 19
- `T10_30M`: 3
- `T0_10M`: 1
- `POST_KICKOFF`: 3

Observed lead-time range: approximately `-3,832` to `1,205` minutes.

This proves that the raw archive contains repeated observations across lifecycle windows, but also that a small number of archived odds responses are post-kickoff and must never be treated as Closing.

## D. Historical Production coverage

The forensic matcher found:

- `FULLY_AUDITABLE`: 0
- `PARTIAL`: 10
- `UNRECOVERABLE`: 4

The four exact Production records with no matching archived odds evidence are:

1. `1637609_UNDER_2_5` — Deportivo Cali W vs Orsomarso W — fixture `1637609` — bookmaker `8`.
2. `1601522_OVER_2_5` — **Hellas Verona vs Arezzo** — fixture `1601522` — bookmaker `8`.
3. `1585746_UNDER_2_5` — Mardin 1969 vs Bodrum FK — fixture `1585746` — bookmaker `8`.
4. `1576480_OVER_2_5` — Lusitânia Lourosa vs AVS — fixture `1576480` — bookmaker `11`.

For these exact fixture IDs the audited raw archive contained no odds response record, so the system must not manufacture Opening/Pick/Closing evidence for them.

## E. Strong Signals evidence

Real `intraday_alerts.json` records contain:

- fixture/prediction/signal identity,
- machine market code plus display field,
- Pick odd and opposite odd,
- bookmaker ID/name,
- odds capture timestamp,
- model/calibration/decision values,
- signal source/type,
- status and settlement result,
- `closing_5m_odd`, `closing_5m_opposite_odd`, `closing_5m_odds_captured_at` fields.

The audited records include examples where these T-5 closing fields are all `null` despite a settled counterfactual result. That is a persistence/linkage failure, not a reason to fabricate a close.

## F. Scheduler/cadence evidence

Current workflow schedules observed in the audit branch:

- `daily.yml`: `*/5 * * * *`
- `bulletin-watchdog.yml`: `2-59/5 * * * *`
- `closing-capture.yml`: `*/5 * * * *`
- `monitor.yml`: `*/5 * * * *`
- `watchlist.yml`: `*/2 6-23 * * *`
- `intraday.yml`: `*/30 6-23 * * *`
- `settlement-watchdog.yml`: `*/10 * * * *`

Recent Actions history available to the CI audit contained 3 scheduled runs in its first 100 runs:

- Monitor odds and settle ledgers — failed
- QuantBet settlement watchdog — failed
- Deploy QuantBet dashboard — succeeded

Therefore the production scheduler cannot yet be considered fully proven by the mere existence of cron declarations.

## G. Root-cause direction

The correct repair is not to fill UI fields. It is to create one canonical lifecycle service/contract that:

1. identifies the exact fixture + market + selection + bookmaker,
2. records immutable observed quotes with source provenance,
3. selects Opening as the earliest valid pre-pick observation,
4. preserves Pick as the exact decision-entry quote,
5. selects Closing deterministically from the final valid pre-kickoff observation under the existing T-5 rule,
6. links Production and Strong Signals to the same observation IDs while keeping accounting separate,
7. persists reason-coded failures instead of silently dropping lifecycle stages,
8. reconstructs historical records idempotently from the raw archive,
9. renders one canonical public contract.

## H. Guardrails

- No bookmaker substitution.
- No fabricated timestamps, odds, CLV or logos.
- No rewrite of immutable raw observations.
- No change to Dixon-Coles/model probabilities.
- No change to calibration.
- No change to EV/edge/risk/Kelly mathematics.
- No change to eligibility/business rules.
- No merge of Production and Strong Signals accounting.
- CLV mathematics remains unchanged.

## Audit gate status

**PASS — Phase 0 complete.** This report is attached to the Issue #50 implementation PR before the product lifecycle repair phase.
