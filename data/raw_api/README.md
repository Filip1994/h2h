# QuantBet raw API archive

This directory contains the durable research archive of successful API responses observed by production runs.

## Format

- One UTF-8 JSONL file per UTC calendar day: `YYYY-MM-DD.jsonl`.
- One record per successful network API response (cache hits are not duplicated).
- Each record contains the archive schema version, UTC capture timestamp, endpoint, request parameters, a safe request URL without credentials, API request sequence number, GitHub Actions provenance when available, and the full parsed API payload.

## Retention

The archive is intentionally append-only during the observation period. Do not rewrite, backfill, or delete records while collecting the 14-30 day research dataset.

## Privacy / secrets

API credentials are never included in the archived URL or payload metadata. The authentication header is not persisted.
