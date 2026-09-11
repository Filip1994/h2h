# QuantBet Football — Complete Production System Audit

**Audit date:** 2026-09-11  
**Repository:** `Filip1994/h2h`  
**Production branch audited:** `main`  
**Identity hardening branch:** `production/observation-identity-v3`

## Executive conclusion

The Production system is a GitHub Actions-driven, file-backed football decision and odds-lifecycle system. The authoritative Production state is still the repository state (`bets.json`, `predictions.json`, lifecycle snapshots and derived dashboard), while Railway is used as an external persistence/archive layer. The browser/dashboard is derived and does not query the provider directly.

The audit found one important identity-layer defect and one important storage/scale boundary:

1. `observation_id` existed conceptually but was not consistently persisted by `OddsSnapshotStore`, while `odds_lifecycle.py` expected it. The Production identity chain was therefore incomplete.
2. Raw provider API archives have grown to very large JSONL files in the repository working tree. The four visible raw archives dated 2026-09-07 through 2026-09-10 total about **276.9 MB**. This is a poor long-term Git storage pattern and is the main structural reason the system will eventually hit memory/disk limits if raw data continues to be treated as repository state.

The identity issue has now been resolved on `production/observation-identity-v3` using the agreed semantic contract:

> **Observation ID = deterministic identity of one normalized bookmaker quote state.**

The selected model is **Model 2 + immutable snapshot record**:

- `observation_id` identifies the quote state;
- `snapshot_id` identifies the immutable observation record;
- `captured_at`, lifecycle type and request provenance belong to the snapshot/evidence layer, not the semantic quote identity.

Legacy snapshot rows are not rewritten. They are enriched in memory with the new observation identity when read. New records persist the observation identity explicitly.

---

# 1. System boundary

## Production flow

```text
API-Football
    │
    ▼
APIFootballClient
    │
    ├── request quota governor
    ├── short-lived API cache
    └── raw response archive
    │
    ▼
fixture / odds normalization
    │
    ▼
Dixon-Coles point-in-time model
    │
    ▼
market probability
    │
    ▼
bookmaker quote + same-bookmaker de-vig
    │
    ▼
EV / probability-edge gates
    │
    ▼
risk allocation
    │
    ▼
Production Pick + decision packet
    │
    ▼
immutable odds snapshots
    │
    ▼
Opening → Pick → Current/Live → Closing
    │
    ▼
settlement / CLV / calibration evidence
    │
    ▼
production_dashboard.json
```

The architecture document explicitly separates H2H research artifacts from the Production flow. H2H does not determine Production eligibility, probability, EV, edge, stake or selection.

---

# 2. What is authoritative?

There are several different truths. They must not be conflated.

| Layer | Authority | Meaning |
|---|---|---|
| Provider response | Raw API response | What the upstream provider returned |
| Snapshot store | `data/odds_snapshots.jsonl` | What QuantBet normalized and accepted as an observation |
| Observation ID | canonical identity | Which quote state the observation represents |
| Snapshot ID | immutable record identity | Which exact stored observation record this is |
| Decision packet | `bets.json` embedded packet | What the model/strategy decided and with which inputs |
| Lifecycle | derived from snapshots + bet | Opening/Pick/Current/Closing interpretation |
| Dashboard | `production_dashboard.json` | Human-readable derived operational view |
| Railway Bucket | external archive | Durable raw API evidence copy |
| Railway Postgres | archive/migration store | External structured archive; not the live Production source of truth |

This separation is intentional.

---

# 3. Canonical Observation ID — final semantic contract

## Definition

`Observation ID` means:

> **The deterministic identity of one normalized bookmaker market quote state.**

Identity fields:

```text
fixture_id
market
bookmaker_id
selection
odd
opposite_odd
```

The values are normalized before hashing. Odds are normalized to four decimal places.

## Explicitly excluded from Observation ID

```text
captured_at
snapshot_type
source_request_hash
source_endpoint
prediction_id
signal_id
bet_id
```

Those fields describe evidence, provenance or lifecycle context. They do not change what quote state was observed.

## Consequence

The same quote state observed at different times has the same `observation_id`:

```text
Copenhagen / BTTS YES / Bet365 / 1.95 / 1.80
       │
       ├── 02:42  → same observation_id
       ├── 02:47  → same observation_id
       └── 07:30  → same observation_id
```

When price changes:

```text
1.95 / 1.80 → Observation A
1.91 / 1.91 → Observation B
```

A new `observation_id` is created.

This is exactly the desired semantic behavior.

---

# 4. Canonical identity model — Model 2 + immutable snapshot record

The production implementation now separates semantic identity from event storage.

## Observation identity

The canonical identity function is centralized in:

`src/quantbot/observation_identity.py`

It uses a versioned identity contract (`version = 1`) so future identity changes can be explicit migrations rather than accidental hash changes.

## Immutable snapshot record

`src/quantbot/persistence.py` continues to generate a separate `snapshot_id`.

A snapshot record contains, among other fields:

```text
snapshot_id
observation_id
fixture_id
market
bookmaker_id
selection
odd
opposite_odd
odds_captured_at
snapshot_type
source_endpoint
source_request_hash
prediction_id
signal_id
bet_id
captured_by
```

Therefore:

```text
              QUOTE STATE
            observation_id
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   snapshot 1  snapshot 2  snapshot 3
   02:42       02:47       07:30
```

All three snapshots may refer to the same quote state.

This is the correct model for forensic work because it preserves both:

- semantic identity of the market state;
- immutable evidence of when that state was observed.

---

# 5. Legacy data migration policy

Existing `data/odds_snapshots.jsonl` rows were created under schema v2 and do not all contain `observation_id`.

They are **not rewritten**.

When loaded, legacy rows are deterministically enriched in memory with the new v1 observation identity. The persisted bytes remain unchanged.

This preserves the append-only/immutable property of the historical snapshot store.

New rows use snapshot schema v3 and persist both `observation_id` and `snapshot_id`.

Historical decision packets remain valid legacy packets. New decision packets use schema v3 and the new identity contract.

---

# 6. Decision packet

`src/quantbot/decision_packet.py` now uses the same canonical identity function as the snapshot layer.

New packets contain:

```text
schema_version = 3
pick_observation_id
provenance.canonical_observation_id
provenance.observation_identity
provenance.canonical_observation
integrity_hash
```

The canonical observation payload retains timestamp and lifecycle metadata for audit context, but those fields do not participate in the semantic identity hash.

The packet remains self-verifying through `integrity_hash`.

This removes the prior split where `decision_packet.py` generated one hash definition while `odds_lifecycle.py` contained another.

---

# 7. Production generation — start to finish

`main.py generate` creates the daily Production decision.

`QuantEngine.generate()` performs the following stages:

1. Load Production settings.
2. Load existing bets.
3. Discover fixtures.
4. Apply central eligibility gate.
5. Build point-in-time training data.
6. Fit Dixon-Coles at the decision timestamp.
7. Generate market probabilities.
8. Retrieve valid bookmaker quotes.
9. Compute same-bookmaker de-vig probability and overround.
10. Apply probability haircut.
11. Apply EV gate.
12. Apply probability-edge gate.
13. Allocate risk/stake.
14. Create prediction records.
15. Create Production bets.
16. Create immutable decision packet.
17. Persist the Production ledger.
18. Build the human-readable Production view.
19. Archive raw provider evidence to Railway Bucket.
20. Commit the required Production state to Git.

The model explicitly excludes fixtures at or after the decision timestamp from its training data, preserving point-in-time integrity.

---

# 8. Odds collector — start to finish

`production-odds.yml` runs every five minutes and calls:

```text
python main.py capture-odds
```

The collector discovers fixtures over a three-day horizon and uses cadence based on time-to-kickoff:

| Time to kickoff | Target cadence |
|---|---:|
| >72h | 24h |
| >48h | 24h |
| >24h | 8h |
| >6h | 2h |
| >3h | 30m |
| >1h | 15m |
| <=1h | 5m |

Each due fixture is queried, valid quotes are normalized, and each accepted quote is appended to the immutable snapshot store.

Around five minutes before kickoff the snapshot type can become `T5`.

The collector also writes coverage and operational metrics.

The workflow then:

1. builds the Production lifecycle view;
2. asserts odds freshness;
3. uploads raw API evidence to Railway Bucket;
4. commits immutable Production observations.

---

# 9. Current odds example — Copenhagen

At the audited Production state, Copenhagen / Horsens had:

```text
PICK:    1.95
CURRENT: 1.91
Book:    Bet365
Market:  BTTS_YES
```

The `1.91` current quote was found as an exact persisted snapshot in `data/odds_snapshots.jsonl`.

The chain was:

```text
API request identity
        ↓
normalized odds parser
        ↓
immutable persisted snapshot
        ↓
observation identity
        ↓
CURRENT lifecycle selection
        ↓
production dashboard
```

The important limitation remains that the Git repository alone cannot prove the exact original provider JSON payload at that instant when the raw archive is not present in the repository. The raw evidence archive is therefore correctly being moved to Railway Bucket as the durable evidence layer.

Also, the API client uses a 120-second odds cache. Consequently, `odds_captured_at` is the system observation timestamp, not a cryptographic claim that the upstream HTTP response physically arrived at that exact second. The raw API archive is the stronger provenance record.

---

# 10. Lifecycle semantics

The lifecycle resolver now operates on the canonical quote-state identity while retaining immutable event records.

## FIRST_SEEN / Opening

Earliest valid persisted observation for the exact:

```text
fixture + market + bookmaker + selection
```

No look-ahead.

## PICK

Exact `ENTRY` observation at the Production decision timestamp.

## CURRENT / LIVE

Latest persisted observation strictly after PICK and before kickoff, available at dashboard build time.

Post-kickoff data cannot become CURRENT.

## CLOSING

Final valid pre-kickoff observation under the closing contract.

If a true T5/CLOSING observation is unavailable, the system can recover a valid near-kickoff pre-kickoff observation according to the existing recovery rules and marks that recovery explicitly.

## CLV

```text
CLV = Pick Odd / Closing Odd - 1
```

CLV remains `NOT_COMPUTABLE` when the required evidence does not exist.

The system does not fabricate missing lifecycle stages.

---

# 11. What is stored where?

## GitHub repository — live Production state

### Primary Production state

- `bets.json` — Production decision ledger.
- `predictions.json` — prediction/calibration ledger.
- `ledger_meta.json` — bank/mode/model metadata.
- `production_dashboard.json` — derived dashboard state.

### Odds evidence

- `data/odds_snapshots.jsonl` — canonical normalized immutable odds snapshots.
- `data/odds_collection_coverage.jsonl` — collector coverage/outcome events.
- `odds_collection_state.json` — collector scheduling state.
- `odds_collection_budget.json` — daily collector budget state.
- `odds_collection_metrics.json` — latest collector metrics.

### Other operational state

- `api_usage.json`
- `api_usage_history.json`
- `generation_health.json`
- `generation_health_history.json`
- `data/football_api_quota.json`
- `production_operations_gate.md`

### Analytical/signal surfaces

- `intraday_signal_events.jsonl`
- `market_timing_snapshots.jsonl`
- Strong/Near signal ledgers and watchlist state.

These do not alter Production accounting.

---

# 12. Raw API evidence

`src/quantbot/api.py` writes raw provider responses as daily JSONL files under:

```text
data/raw_api/YYYY-MM-DD.jsonl
```

Each raw record includes:

```text
captured_at
endpoint
params
request_url
request_count
GitHub workflow metadata
GitHub SHA
payload
```

The API client writes each response line with flush + fsync.

The repository `.gitignore` already excludes `data/raw_api/*.jsonl`, but historical raw files had previously been committed. The identity branch removes the currently visible large raw archive files from the Git working tree. This does not erase the old blobs from Git history; history rewriting is a separate operation and should not be done casually on Production.

The Production workflows already upload the raw archive to Railway Bucket as gzip-compressed objects.

---

# 13. Railway architecture

The current Railway migration design has two separate external persistence paths.

## Railway Bucket

Purpose:

> **Immutable raw API evidence archive.**

Current workflow key pattern:

```text
quantumbet/raw-api/live/YYYY-MM-DD.jsonl.gz
```

The migration workflow also uses:

```text
quantumbet/raw-api/YYYY-MM-DD.jsonl.gz
```

The object metadata carries the SHA-256 of the original JSONL file.

## Railway Postgres

The migration workflow imports structured repository state into:

```text
quantumbet_archive_records
quantumbet_archive_manifest
```

This is an external archive/query surface. It is not currently the live Production dashboard source of truth.

That distinction should remain unless a future controlled migration explicitly promotes Railway to the live transactional source.

---

# 14. Current storage growth observed in Git

The current `data/` tree contains approximately:

| File | Bytes | Approx. size |
|---|---:|---:|
| `odds_snapshots.jsonl` | 9,575,907 | 9.6 MB |
| `raw_api/2026-09-07.jsonl` | 1,449,202 | 1.4 MB |
| `raw_api/2026-09-08.jsonl` | 98,348,863 | 98.3 MB |
| `raw_api/2026-09-09.jsonl` | 72,287,167 | 72.3 MB |
| `raw_api/2026-09-10.jsonl` | 104,796,411 | 104.8 MB |

The four visible raw archives total:

**276,881,643 bytes ≈ 276.9 MB decimal ≈ 264 MiB.**

Average over those four days:

**≈69.2 MB/day of uncompressed raw API archive.**

At that observed rate, 5 GB of storage would represent roughly **72 days** of raw uncompressed data.

This is only a planning estimate. Provider response volume changes with fixture count, bookmaker coverage, retry behavior and API response size.

---

# 15. Why memory fills before storage fills

Storage growth and process memory growth are different problems.

A 100 MB JSONL file does not automatically require 100 MB RAM. The problem appears when code does something like:

```python
path.read_text()
```

or:

```python
json.loads(whole_file)
```

or:

```python
path.read_text().splitlines()
```

because the process may simultaneously hold:

- the complete text string;
- split line strings;
- parsed Python dictionaries/lists;
- temporary JSON objects;
- downstream transformed structures.

A 100 MB file can therefore consume several hundred MB of RAM or more depending on object expansion.

The repository contains code paths that load JSONL collections into Python lists, so file size growth must be controlled independently of storage capacity.

The correct long-term solution is **not** to keep buying more RAM or move from 5 GB to 1 TB storage.

---

# 16. How production systems normally solve this

The standard pattern is:

```text
RAW INGEST
   ↓
Object Storage
   ↓
Partition by date / source / dataset
   ↓
Immutable compressed archive
   ↓
Normalize only the records needed for active computation
   ↓
Queryable structured store
   ↓
Curated analytics format
```

For large historical datasets, raw data is commonly retained in object storage rather than Git. A raw layer is kept immutable, while transformed/curated layers are optimized for querying.

For analytics workloads, columnar formats such as Parquet are commonly used for transformed data because they reduce storage footprint and avoid repeatedly parsing huge JSON documents.

This is the right direction for QuantBet as volume grows.

---

# 17. QuantBet's recommended storage policy

## Tier 1 — GitHub

Keep only:

- current Production ledger;
- current dashboard;
- small operational state;
- normalized snapshot history while it remains operationally manageable;
- source code;
- documentation.

Do **not** use Git as the raw API data lake.

## Tier 2 — Railway Bucket

Keep:

- immutable raw API JSONL.gz;
- one object per UTC day;
- SHA-256 metadata;
- lifecycle/retention policy.

This is where the raw evidence should scale.

## Tier 3 — Railway Postgres

Keep/query:

- structured archive records;
- manifests;
- decision and lifecycle metadata when useful for SQL analysis.

## Tier 4 — Future analytical archive

If snapshot volume becomes large enough, periodically transform historical JSONL into compressed columnar storage such as Parquet and retain it in object storage.

Do not introduce this complexity prematurely. The current normalized snapshot file is only about 9.6 MB, while raw API archives are already hundreds of MB.

---

# 18. Railway 5 GB — is it enough?

## For raw API archive: yes as a short-term buffer, but not as the long-term architecture.

Railway currently documents:

- Hobby: 5 GB default volume;
- Pro: volumes can be resized, with self-service up to 1 TB;
- Enterprise: up to 5 TB;
- Railway Buckets are separately priced object storage and are designed for large object-storage workloads.

Therefore **do not upgrade a Railway volume to 1 TB just because raw API logs are growing**.

The correct move is to put raw API evidence in the Railway Bucket, which QuantBet is already doing.

The current Railway Bucket pricing is dramatically cheaper per GB-month than a Railway volume and is the more appropriate storage class for immutable raw archives.

---

# 19. What happens when storage grows to 100 GB / 500 GB / 1 TB?

The system should not care.

The important rule is:

> Active computation must not require loading the entire historical archive into memory.

At 1 TB of historical raw evidence, a production system still does not load 1 TB into RAM. It reads only the relevant partitions/objects for the task.

For QuantBet that means:

```text
Today's odds work
    → today's / relevant recent objects

Historical audit
    → selected date partitions

Model research
    → curated dataset

Full archive
    → object storage, not RAM
```

This is the scalable boundary.

---

# 20. GitHub Actions memory strategy

The current `ubuntu-latest` GitHub-hosted runner is documented with 16 GB RAM and 14 GB SSD for public repositories. Larger runners are available for organizations/enterprises with configurations such as 16, 32, 64, 128 GB RAM and more.

However, a larger runner should be treated as **headroom**, not as the primary data architecture.

Correct order of operations:

1. Stop committing raw API archives to Git.
2. Upload raw API archives directly to object storage.
3. Stream large JSONL files instead of `read_text().splitlines()` where possible.
4. Read only the relevant date/fixture partition.
5. Keep normalized active snapshot state small.
6. Use a larger runner only when the actual computation itself needs more RAM.

This is how systems scale without turning storage growth into a memory requirement.

---

# 21. Production readiness status

## PASS — identity contract

Canonical quote-state identity is now centralized and versioned.

## PASS — immutable snapshot separation

`observation_id` and `snapshot_id` have distinct semantics.

## PASS — legacy compatibility

Old snapshot rows are not rewritten and can be assigned the new identity in memory.

## PASS — decision provenance

New decision packets use the same identity function as the snapshot layer.

## PASS — lifecycle semantics

Opening/Pick/Current/Closing remain timestamp- and kickoff-aware.

## PASS — raw evidence architecture

Raw API evidence is already being uploaded to Railway Bucket with SHA-256 metadata.

## PASS — dashboard derivation

Dashboard remains derived from persisted Production state and does not call the provider API.

## PASS — API quota separation

The odds collector has its own concurrency group and global quota governor remains the central API accounting boundary.

## PASS — tests expanded

The identity branch adds dedicated tests for:

- stable quote-state identity across time;
- identity change on price change;
- immutable snapshot separation;
- legacy in-memory identity enrichment;
- decision packet identity consistency;
- lifecycle compatibility.

The test workflow is expanded to run the complete test suite and lint the identity-layer modules.

## REMAINING operational boundary — Git history

Deleting the large historical raw API files from the working tree does not remove their blobs from Git history. If repository clone size or historical object storage becomes a problem, a separately planned Git history rewrite is required. That should be treated as an explicit repository migration, not an incidental cleanup.

## REMAINING evidence boundary — raw provider payload

The normalized snapshot proves what QuantBet stored. The raw API archive proves what the provider returned. Those should remain separate evidence layers.

---

# 22. Final production data model

```text
                         API PROVIDER
                              │
                              ▼
                     RAW API RESPONSE
                              │
                    immutable raw archive
                              │
                              ▼
                    NORMALIZED QUOTE
                              │
             ┌────────────────┴────────────────┐
             │                                 │
             ▼                                 ▼
     observation_id                       snapshot_id
     QUOTE STATE IDENTITY                 EVENT RECORD ID
             │                                 │
             │                         ┌───────┼────────┐
             │                         ▼       ▼        ▼
             │                       time   lifecycle provenance
             │
             ▼
       PICK / CURRENT / CLOSING
             │
             ▼
      DECISION + CLV + SETTLEMENT
             │
             ▼
       PRODUCTION DASHBOARD
```

This is the target production contract.

The key architectural principle is:

> **Identity tells us what the quote is. Snapshot evidence tells us when and how we observed it. The lifecycle tells us what role that observation played. The decision packet tells us why the system acted.**

That separation is what makes the system reconstructable instead of merely functional.
