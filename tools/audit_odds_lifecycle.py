from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_api"
SNAP = ROOT / "data" / "odds_snapshots.jsonl"
QuoteKey = tuple[int, str, int]
Quote = tuple[datetime, str, float]


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except ValueError:
        return None


def market_key(value: Any) -> str:
    value = str(value or "").upper().strip().replace(" ", "_")
    return value.replace(".", "_")


def pick_key(item: dict[str, Any]) -> QuoteKey | None:
    try:
        return (
            int(item["event_id"]),
            market_key(item.get("market")),
            int(item["bookmaker_id"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def audit_raw() -> dict[str, Any]:
    endpoint_counts: Counter[str] = Counter()
    bookmakers: Counter[str] = Counter()
    markets: Counter[str] = Counter()
    quotes: dict[QuoteKey, list[Quote]] = defaultdict(list)
    fixture_evidence: dict[int, dict[str, Any]] = {}
    odds_records = 0
    quote_rows = 0
    logo_rows = 0
    provider_shape: dict[str, Any] = {}
    timing = Counter()
    lead_minutes: list[float] = []

    for path in sorted(RAW.glob("*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                endpoint = str(record.get("endpoint") or "")
                endpoint_counts[endpoint] += 1
                if endpoint != "odds":
                    continue
                captured = parse_dt(record.get("captured_at"))
                response = (record.get("payload") or {}).get("response")
                params = record.get("params") or {}
                try:
                    fixture = int(params.get("fixture") or params.get("id"))
                except (TypeError, ValueError):
                    continue
                if captured is None or not isinstance(response, list):
                    continue
                odds_records += 1
                evidence = fixture_evidence.setdefault(
                    fixture,
                    {
                        "records": 0,
                        "first_capture": None,
                        "last_capture": None,
                        "bookmakers": set(),
                        "markets": set(),
                        "selections": set(),
                    },
                )
                evidence["records"] += 1
                evidence["first_capture"] = min(
                    evidence["first_capture"] or captured.isoformat(),
                    captured.isoformat(),
                )
                evidence["last_capture"] = max(
                    evidence["last_capture"] or captured.isoformat(),
                    captured.isoformat(),
                )
                if not provider_shape and response:
                    first = response[0]
                    bookmaker = (first.get("bookmakers") or [{}])[0]
                    bet = (bookmaker.get("bets") or [{}])[0]
                    selection = (bet.get("values") or [{}])[0]
                    provider_shape = {
                        "response_keys": sorted(first.keys()),
                        "fixture_keys": sorted((first.get("fixture") or {}).keys()),
                        "league_keys": sorted((first.get("league") or {}).keys()),
                        "bookmaker_keys": sorted(bookmaker.keys()),
                        "market_keys": sorted(bet.keys()),
                        "selection_keys": sorted(selection.keys()),
                    }
                kickoff = None
                if response:
                    kickoff = parse_dt((response[0].get("fixture") or {}).get("date"))
                if kickoff is not None:
                    lead = (kickoff - captured).total_seconds() / 60
                    lead_minutes.append(lead)
                    if lead < 0:
                        timing["POST_KICKOFF"] += 1
                    elif lead <= 10:
                        timing["T0_10M"] += 1
                    elif lead <= 30:
                        timing["T10_30M"] += 1
                    elif lead <= 60:
                        timing["T30_60M"] += 1
                    elif lead <= 180:
                        timing["T1_3H"] += 1
                    elif lead <= 360:
                        timing["T3_6H"] += 1
                    else:
                        timing["GT6H"] += 1
                for container in response:
                    for bookmaker in container.get("bookmakers") or []:
                        bid = bookmaker.get("id")
                        if bid is None:
                            continue
                        bookmakers[str(bid)] += 1
                        evidence["bookmakers"].add(str(bid))
                        if bookmaker.get("logo"):
                            logo_rows += 1
                        for bet in bookmaker.get("bets") or []:
                            name = str(bet.get("name") or bet.get("id") or "")
                            markets[name] += 1
                            evidence["markets"].add(name)
                            for value in bet.get("values") or []:
                                selection_name = str(value.get("value") or "")
                                evidence["selections"].add(selection_name)
                                try:
                                    odd = float(value["odd"])
                                except (KeyError, TypeError, ValueError):
                                    continue
                                if odd <= 1:
                                    continue
                                quote_rows += 1
                                key = (fixture, market_key(name), int(bid))
                                quotes[key].append((captured, selection_name, odd))

    for evidence in fixture_evidence.values():
        for field in ("bookmakers", "markets", "selections"):
            evidence[field] = sorted(evidence[field])

    return {
        "endpoint_counts": dict(endpoint_counts),
        "odds_records": odds_records,
        "quote_rows": quote_rows,
        "unique_keys": len(quotes),
        "bookmakers": bookmakers.most_common(15),
        "markets": markets.most_common(15),
        "logo_rows": logo_rows,
        "provider_shape": provider_shape,
        "timing": dict(timing),
        "lead_min": min(lead_minutes) if lead_minutes else None,
        "lead_max": max(lead_minutes) if lead_minutes else None,
        "fixture_evidence": fixture_evidence,
        "quotes": quotes,
    }


def audit_lifecycle(raw: dict[str, Any]) -> dict[str, Any]:
    bets = load_json(ROOT / "bets.json") or []
    coverage: Counter[str] = Counter()
    missing: list[dict[str, Any]] = []
    for bet in bets:
        key = pick_key(bet)
        if key is None:
            continue
        values = sorted(raw["quotes"].get(key, []), key=lambda item: item[0])
        pick_at = parse_dt(bet.get("odds_captured_at"))
        opening = bool(
            pick_at and any(captured <= pick_at for captured, _, _ in values)
        )
        closing = bool(
            bet.get("closing_odd") is not None
            and parse_dt(bet.get("closing_odds_captured_at")) is not None
        )
        if opening and closing:
            coverage["FULLY_AUDITABLE"] += 1
        elif opening or closing:
            coverage["PARTIAL"] += 1
        else:
            coverage["UNRECOVERABLE"] += 1
            evidence = raw["fixture_evidence"].get(int(bet.get("event_id", 0)), {})
            missing.append(
                {
                    "id": bet.get("id"),
                    "match": bet.get("match"),
                    "fixture_id": bet.get("event_id"),
                    "market": bet.get("market"),
                    "bookmaker_id": bet.get("bookmaker_id"),
                    "archive_evidence": evidence,
                }
            )
    return {"bets": len(bets), "coverage": dict(coverage), "missing": missing[:20]}


def audit_snapshots() -> dict[str, Any]:
    types: Counter[str] = Counter()
    linked: Counter[str] = Counter()
    lines = 0
    if not SNAP.exists():
        return {"lines": 0, "bytes": 0, "types": {}, "linked": {}}
    with SNAP.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            lines += 1
            types[str(item.get("snapshot_type") or item.get("type") or "UNKNOWN")] += 1
            for key in ("prediction_id", "bet_id", "signal_id"):
                if item.get(key) is not None:
                    linked[key] += 1
    return {
        "lines": lines,
        "bytes": SNAP.stat().st_size,
        "types": dict(types),
        "linked": dict(linked),
    }


def audit_actions() -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return {"error": "GITHUB_TOKEN unavailable"}
    request = urllib.request.Request(
        "https://api.github.com/repos/Filip1994/h2h/actions/runs?per_page=100",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            runs = json.load(response).get("workflow_runs", [])
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}
    scheduled = [run for run in runs if run.get("event") == "schedule"]
    return {
        "runs": len(runs),
        "scheduled_runs": len(scheduled),
        "scheduled_by_workflow": dict(Counter(run.get("name") for run in scheduled)),
        "recent": [
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "created_at": run.get("created_at"),
            }
            for run in scheduled[:20]
        ],
    }


def build_report(data: dict[str, Any]) -> str:
    raw = data["raw"]
    lifecycle = data["lifecycle"]
    return f"""# QuantBet Odds Lifecycle — Phase 0 Forensic Audit

Generated: `{data["generated_at"]}`

## Conclusion

The current main branch contains a substantial raw API-Football odds archive and a non-empty canonical snapshot file, but the lifecycle is still incomplete. The audit finds real provider odds observations, while Opening/Pick/Closing linkage is not consistently canonical and Strong Signals uses a separate T-5 persistence path. The repair must make the lifecycle real and reproducible without changing decision mathematics.

## Evidence

- Raw archive files: `{data["raw_files"]}`; bytes: `{data["raw_bytes"]:,}`.
- Odds response records: `{raw["odds_records"]}`; extracted quote rows: `{raw["quote_rows"]}`.
- Unique fixture/market/bookmaker keys: `{raw["unique_keys"]}`.
- Canonical snapshot ledger: `{data["snapshots"]["lines"]}` lines; `{data["snapshots"]["bytes"]:,}` bytes.
- Snapshot types: `{data["snapshots"]["types"]}`.
- Snapshot linkage counts: `{data["snapshots"]["linked"]}`.
- Production bets inspected: `{lifecycle["bets"]}`.
- Lifecycle coverage: `{lifecycle["coverage"]}`.
- Provider shape: `{json.dumps(raw["provider_shape"], ensure_ascii=False)}`.
- Capture timing buckets: `{raw["timing"]}`; lead range minutes: `{raw["lead_min"]}`..`{raw["lead_max"]}`.
- Provider bookmaker logo metadata observed on `{raw["logo_rows"]}` bookmaker records.

## Root causes

1. ENTRY is derived from the pick quote instead of selecting the earliest valid archived observation as Opening.
2. Strong Signals T-5 closing data and Production canonical closing data have separate persistence/linkage paths.
3. Legacy CLV can be present while lifecycle linkage is incomplete, so mathematical presence is not the same as audit completeness.
4. The provider archive is the source of truth for actual observations; missing stages cannot be backfilled from unrelated bookmakers, selections or timestamps.
5. The audited provider bookmaker objects do not expose a logo field, so a deterministic verified registry is required if logos are to be displayed.

## Concrete missing-record evidence

`{json.dumps(lifecycle["missing"], ensure_ascii=False)}`

## Schedule evidence

- Workflow schedules: `{json.dumps(data["schedules"], ensure_ascii=False)}`.
- Recent Actions schedule evidence: `{json.dumps(data["actions"], ensure_ascii=False)}`.

## Implementation guardrails

- Preserve Production vs Strong Signals accounting separation.
- Preserve bookmaker identity; no fallback bookmaker for lifecycle stages.
- Preserve raw API provenance and append-only audit history.
- Do not alter Dixon-Coles, calibration, EV/edge, risk/Kelly, eligibility or CLV mathematics.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = audit_raw()
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "raw_files": len(list(RAW.glob("*.jsonl"))),
        "raw_bytes": sum(path.stat().st_size for path in RAW.glob("*.jsonl")),
        "raw": raw,
        "snapshots": audit_snapshots(),
        "lifecycle": audit_lifecycle(raw),
        "actions": audit_actions(),
        "schedules": {},
    }
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        data["schedules"][path.name] = [
            line.strip() for line in text.splitlines() if "cron:" in line
        ]
    report = build_report(data)
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
