# H2H Research Dataset v1.0

## Purpose

`data/h2h_snapshots.jsonl` is the canonical, append-only point-in-time H2H research store. H2H telemetry is observational only and has zero authority over model probability, calibration, decision probability, EV, edge, selection, stake sizing, risk, market choice, or live/paper mode.

## Snapshot identity

`h2h_snapshot_id = SHA256(fixture_id + "|" + data_cutoff_UTC)`.

The same fixture at a later cutoff is a new snapshot. Existing snapshots are never overwritten.

## Point-in-time rule

Only H2H matches with `match.date < data_cutoff` are eligible. Future matches must never enter a snapshot. `decision_timestamp` and `data_cutoff` are the same decision-time cutoff used by the engine.

## Schema

Each record contains:

- `schema_version`
- `h2h_snapshot_id`
- fixture/team/league identity
- `decision_timestamp`, `data_cutoff`, `captured_at`
- `h2h_enabled`, `h2h_available`, `h2h_status`, `h2h_error`
- `h2h_rate`, `h2h_n`, `h2h_effective_n`, `h2h_has_recent_match`
- `h2h_rates` for `OVER_2_5`, `UNDER_2_5`, `BTTS_YES`
- full normalized `h2h_matches`
- `source_endpoint`, `source_request_hash`, `captured_by`

The canonical status values are:

- `AVAILABLE`
- `INSUFFICIENT_HISTORY`
- `NO_RECENT_HISTORY`
- `API_ERROR`
- `PARSE_ERROR`
- `NOT_REQUESTED`

Unavailable H2H is represented explicitly; it is never encoded as a meaningful 0% rate.

## Linkage

Every generated prediction receives `h2h_snapshot_id`. A selected production bet copies the same linkage. Intraday signal/near-miss records inherit the linkage from their `prediction_id`; they do not trigger another H2H request.

One fixture generation produces one H2H request and one fixture-level snapshot shared by all generated markets.

## Outcomes

Because snapshots are immutable, final match outcomes are stored in the append-only `data/h2h_outcomes.jsonl` join keyed by `h2h_snapshot_id`.

Outcome fields:

- `final_home_goals`
- `final_away_goals`
- `final_total_goals`
- `final_result_1x2`

`final_result_1x2` uses `1 = home win`, `X = draw`, `2 = away win`.

This is outcome telemetry only. It does not add Moneyline as a production market.

## Historical integrity

No historical H2H snapshot is backfilled from a later API response as if it were known at decision time. Any future reconstruction must be explicitly marked as backfill and must not overwrite OOS telemetry.

## API provenance

The normalized snapshot records the endpoint and deterministic request hash. Raw API responses continue to live in `data/raw_api/*.jsonl`; this dataset does not create a second raw-response archive.

## Coverage validator

Run:

```text
python tools/h2h_telemetry_health.py
```

The validator reports prediction, H2H, selected, signal and canonical snapshot coverage. It is diagnostic only and never a betting gate.

## Moneyline boundary

No `HOME`, `DRAW`, or `AWAY` production market is introduced by this dataset. The only 1/X/2 information stored here is the final match outcome used for future research.
