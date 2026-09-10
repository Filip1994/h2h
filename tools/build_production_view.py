from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.odds_lifecycle import lifecycle_contract, observations_for

BETS = ROOT / "bets.json"
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
METRICS = ROOT / "odds_collection_metrics.json"
OUT = ROOT / "production_dashboard.json"


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def compact_observation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {"observation_id": row.get("observation_id"), "odd": row.get("odd"), "opposite_odd": row.get("opposite_odd"), "captured_at": row.get("odds_captured_at"), "snapshot_type": row.get("snapshot_type"), "bookmaker_id": row.get("bookmaker_id"), "bookmaker": row.get("bookmaker")}


def enrich(bet: dict[str, Any], now: datetime) -> dict[str, Any]:
    try:
        fixture_id, market, bookmaker_id = int(bet["event_id"]), str(bet["market"]), int(bet["bookmaker_id"])
    except (KeyError, TypeError, ValueError):
        fixture_id, market, bookmaker_id = None, "", None
    pick_at, kickoff = parse_dt(bet.get("odds_captured_at") or bet.get("created_at")), parse_dt(bet.get("kickoff"))
    observations = observations_for(SNAPSHOTS, fixture_id=fixture_id, market=market, bookmaker_id=bookmaker_id) if fixture_id is not None and bookmaker_id is not None else []
    contract = lifecycle_contract(observations, pick_at=pick_at, kickoff=kickoff) if pick_at is not None else {"opening": None, "pick": None, "closing": None, "closing_recovered": False, "clv_odds_pct": None}
    latest = observations[-1] if observations else None
    live_ts = parse_dt(latest.get("odds_captured_at")) if latest else None
    age_minutes = max(0.0, (now - live_ts).total_seconds() / 60.0) if live_ts else None
    item = dict(bet)
    item["production_lifecycle"] = {
        "opening": compact_observation(contract.get("opening")),
        "pick": compact_observation(contract.get("pick")) or {"odd": bet.get("odd"), "captured_at": bet.get("odds_captured_at"), "observation_id": bet.get("pick_snapshot_id") or bet.get("pick_observation_id")},
        "live": compact_observation(latest),
        "live_state": "FRESH" if age_minutes is not None and age_minutes <= 15 else "STALE" if age_minutes is not None else "NO_OBSERVATION",
        "live_age_minutes": age_minutes,
        "closing": compact_observation(contract.get("closing")),
        "closing_recovered": bool(contract.get("closing_recovered")),
        "clv_odds_pct": contract.get("clv_odds_pct"),
        "coverage": "FULL" if contract.get("opening") and contract.get("pick") and contract.get("closing") else "PARTIAL",
    }
    return item


def main() -> int:
    now = datetime.now(UTC)
    bets = load_json(BETS, [])
    bets = bets if isinstance(bets, list) else []
    enriched = [enrich(b, now) for b in bets if isinstance(b, dict)]
    active = [b for b in enriched if str(b.get("status", "PENDING")).upper() == "PENDING"]
    history = [b for b in enriched if str(b.get("status", "PENDING")).upper() != "PENDING"]
    meta = load_json(ROOT / "ledger_meta.json", {})
    metrics = load_json(METRICS, {})
    snapshots = load_jsonl(SNAPSHOTS)
    run_at = parse_dt(metrics.get("timestamp"))
    requests_this_run = int(metrics.get("api_requests_used_this_run") or 0)
    last_snapshot = max((parse_dt(r.get("odds_captured_at")) for r in snapshots), default=None)
    run_age = max(0.0, (now - run_at).total_seconds() / 60.0) if run_at else None
    run_state = "FRESH" if run_age is not None and run_age <= 15 and requests_this_run > 0 else "RUN_NO_API" if run_age is not None and run_age <= 15 else "STALE" if run_age is not None else "NO_RUN"
    output = {
        "schema_version": 4,
        "generated_at": now.isoformat(),
        "truth": "data/odds_snapshots.jsonl + bets.json",
        "monitoring": {
            "last_collector_run_at": run_at.isoformat() if run_at else None,
            "last_odds_scan_at": run_at.isoformat() if run_at and requests_this_run > 0 else None,
            "last_snapshot_at": last_snapshot.isoformat() if last_snapshot else None,
            "collector_run_age_minutes": run_age,
            "scan_age_minutes": run_age if requests_this_run > 0 else None,
            "scan_state": run_state,
            "api_requests_last_scan": requests_this_run,
            "daily_budget_used": metrics.get("daily_budget_used"),
            "daily_budget_remaining": metrics.get("daily_budget_remaining"),
            "observations_last_scan": metrics.get("observations_captured"),
        },
        "rules": {"opening": "first real persisted observation for exact fixture/market/bookmaker at or before Pick", "live": "latest real persisted observation for exact fixture/market/bookmaker", "closing": "exact T-2m to T-8m observation, with honest pre-kickoff recovery if missed", "clv": "Pick odd / Closing odd - 1; null when Closing is unavailable", "missing_data": "null; dashboard renders as —"},
        "initial_bank": meta.get("initial_bank", 50000),
        "active": active,
        "history": history,
        "counts": {"production": len(enriched), "active": len(active), "history": len(history), "snapshots": len(snapshots)},
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": output["counts"], "monitoring": output["monitoring"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
