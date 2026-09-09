# Football observation storage boundary

## Decision

Keep the current compact public/audit state in Git, but treat high-volume raw API archives and append-only odds observations as a migration candidate for immutable object/database storage. Do not migrate immediately: the current repository is still below the hard migration threshold, but the observed growth is already high enough to require explicit monitoring.

## Measurement on 2026-09-09

Current Git tree measurements:

| Artifact | Bytes | Approx. size |
|---|---:|---:|
| `data/raw_api/2026-09-07.jsonl` | 1,449,202 | 1.38 MiB |
| `data/raw_api/2026-09-08.jsonl` | 98,348,863 | 93.79 MiB |
| `data/raw_api/2026-09-09.jsonl` (partial) | 24,002,649 | 22.89 MiB |
| `data/odds_snapshots.jsonl` | 1,526,354 | 1.46 MiB |
| `data/market_timing_snapshots.jsonl` | 74,146 | 72.41 KiB |
| `data/intraday_signal_events.jsonl` | 28,216 | 27.55 KiB |
| `predictions.json` | 3,658,330 | 3.49 MiB |

The raw API archive is the dominant growth driver. The three observed raw-archive days total about 123.8 MB, with 2026-09-09 only partial. This is not enough history to claim a stable long-run daily rate, so planning estimates use a conservative **50 MB/day working rate** and explicitly retain the observed 1.4–98 MB/day range as uncertainty.

## Planning envelope at 50 MB/day

| Horizon | Raw API only |
|---|---:|
| 3 months | ~4.5 GB |
| 6 months | ~9.0 GB |
| 12 months | ~18.3 GB |
| 24 months | ~36.5 GB |

These are planning estimates, not guarantees; the actual migration decision must use a rolling 7-day observed rate.

## Migration thresholds

Stay Git-primary while all of the following remain true:

- raw archive rolling 7-day average < **250 MB/day**;
- Git repository total size attributable to raw observations < **5 GB**;
- a normal state-writing workflow completes in < **5 minutes** attributable to Git/data mutation;
- no recurring push/rebase failure is attributable to large observation files;
- Pages/public artifacts remain derived and compact.

Trigger an object/database migration review when **any** threshold is exceeded for 7 consecutive days. Migrate earlier if a single Git operation repeatedly exceeds the workflow timeout or causes data-loss/concurrency incidents.

## Target architecture after migration

- **Git:** code, configuration, compact public JSON, summaries, audit manifests and immutable references.
- **Object/database storage:** raw API responses, full bookmaker observations, lifecycle observation history and other high-volume append-only evidence.
- **Immutable IDs:** canonical observation ID remains deterministic from fixture, market, bookmaker, observation timestamp, odds and snapshot type.
- **Derived public data:** rebuilt deterministically from the canonical observation store and committed/published as compact snapshots.
- **Backup:** daily immutable backup plus periodic reconstruction test.
- **Retention:** raw evidence retained for reproducibility; public derived artifacts can be aggressively compacted without deleting canonical evidence.

## Reconstruction contract

A historical Production decision must be reproducible from its immutable decision packet plus the referenced canonical observation IDs. Moving raw observations out of Git must not change those IDs or rewrite historical packets.

## Operational measurement

Add the following to the storage health report before migration: bytes/day, Git repository bytes, raw-observation bytes, workflow duration, push/rebase retry count and observation count. The migration trigger is based on measured behavior, not aesthetics.
