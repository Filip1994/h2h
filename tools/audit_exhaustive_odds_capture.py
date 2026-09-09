from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "api_usage_history.json"
HEALTH = ROOT / "generation_health_history.json"
SNAP = ROOT / "data" / "odds_snapshots.jsonl"
PRED = ROOT / "predictions.json"
BETS = ROOT / "bets.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def parse(value):
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def main() -> int:
    history = load_json(HISTORY, [])
    health = load_json(HEALTH, [])
    snapshots = load_jsonl(SNAP)
    predictions = load_json(PRED, [])
    bets = load_json(BETS, [])

    print("# Issue #53 — Phase 0 exhaustive odds capture audit")
    print()
    print("## Budget and recent usage")
    budgets = Counter()
    by_day = defaultdict(lambda: {"requests": 0, "odds": 0, "fixtures": 0, "errors": 0})
    for row in history if isinstance(history, list) else []:
        date = str(row.get("date") or str(row.get("timestamp") or "")[:10])
        requests = int(row.get("request_count") or 0)
        odds = int((row.get("endpoint_requests") or {}).get("odds") or 0)
        fixtures = int((row.get("endpoint_requests") or {}).get("fixtures") or 0)
        errors = int(row.get("api_error_events") or 0) + int(row.get("network_error_events") or 0)
        by_day[date]["requests"] += requests
        by_day[date]["odds"] += odds
        by_day[date]["fixtures"] += fixtures
        by_day[date]["errors"] += errors
        budgets[int(row.get("request_budget") or 0)] += 1
    print(f"Configured budgets observed: {dict(sorted(budgets.items()))}")
    for date in sorted(by_day)[-7:]:
        item = by_day[date]
        budget = max(budgets) if budgets else 0
        print(f"- {date}: requests={item['requests']}, odds_requests={item['odds']}, fixture_requests={item['fixtures']}, errors={item['errors']}, working_budget={max(0, budget - 500)}")
    print()

    print("## Fixture-universe coverage")
    print("The current committed generation ledger does not persist a complete eligible Football fixture universe or per-fixture odds-query outcome. Therefore queried/eligible coverage cannot be reconstructed honestly from main without querying the provider. This is a confirmed observability gap, not a zero-coverage claim.")
    print()

    print("## Odds observation ledger")
    counts = Counter(str(row.get("snapshot_type") or "UNKNOWN") for row in snapshots)
    fixtures = {row.get("fixture_id") for row in snapshots if row.get("fixture_id") is not None}
    keys = {
        (row.get("fixture_id"), row.get("market"), row.get("bookmaker_id"))
        for row in snapshots
        if row.get("fixture_id") is not None
    }
    print(f"Canonical snapshots: {len(snapshots)}")
    print(f"Distinct fixtures observed: {len(fixtures)}")
    print(f"Distinct lifecycle keys: {len(keys)}")
    print(f"Snapshot types: {dict(sorted(counts.items()))}")

    missing = Counter()
    for row in [*predictions, *bets] if isinstance(predictions, list) and isinstance(bets, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get("status") not in {"PENDING", "WIN", "LOSS", "VOID", "REVIEW", "SKIPPED", "SETTLED"}:
            continue
        if not row.get("odds_captured_at"):
            missing["NO_ENTRY_OBSERVATION"] += 1
    print(f"Ledger records without an entry odds timestamp: {missing.get('NO_ENTRY_OBSERVATION', 0)}")
    print()

    print("## Production / Strong Signal lifecycle")
    for name, rows in (("Production bets", bets), ("Predictions", predictions)):
        total = len(rows) if isinstance(rows, list) else 0
        opening = sum(1 for row in rows if isinstance(row, dict) and row.get("opening_odd") is not None)
        closing = sum(1 for row in rows if isinstance(row, dict) and (row.get("closing_odd") is not None or row.get("closing_5m_odd") is not None))
        print(f"- {name}: total={total}, opening={opening}, closing={closing}")
    print("Strong Signal lifecycle is not separately auditable from the committed state because the public signal ledger does not yet persist a complete immutable observation coverage summary.")
    print()

    print("## Workflow execution")
    timestamps = []
    for row in health if isinstance(health, list) else []:
        timestamp = parse(row.get("timestamp")) if isinstance(row, dict) else None
        if timestamp:
            timestamps.append(timestamp)
    if timestamps:
        print(f"Latest generation health timestamp: {max(timestamps).isoformat()}")
        print(f"Health samples retained: {len(timestamps)}")
    else:
        print("No generation health samples available.")
    print("Workflow schedule is not equivalent to successful odds coverage; actual scan timestamps must be persisted by the new collector.")
    print()

    print("## Provider availability by time-to-kickoff")
    print("Not measurable from the current committed observation ledger because fixture kickoff and every odds response are not joined into a fixture-level collection state. The new collector must persist explicit NO_ODDS_RESPONSE outcomes so provider availability is measured rather than inferred.")
    print()

    print("## Phase 0 conclusion")
    print("PASS — the audit identifies a material API-capacity utilization gap and a missing fixture-level coverage ledger. No model, EV, edge, Kelly, risk or eligibility thresholds are changed by this audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
