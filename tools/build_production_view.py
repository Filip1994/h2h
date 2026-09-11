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

from quantbot.odds_lifecycle import clv_from_odds, lifecycle_contract, observations_for

BETS = ROOT / "bets.json"
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
METRICS = ROOT / "odds_collection_metrics.json"
OUT = ROOT / "production_dashboard.json"


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
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
    return {
        "observation_id": row.get("observation_id"),
        "odd": row.get("odd"),
        "opposite_odd": row.get("opposite_odd"),
        "captured_at": row.get("odds_captured_at"),
        "snapshot_type": row.get("snapshot_type"),
        "bookmaker_id": row.get("bookmaker_id"),
        "bookmaker": row.get("bookmaker"),
        "selection": row.get("selection"),
    }


def bulletin_pick(bet: dict[str, Any]) -> dict[str, Any] | None:
    """Daily Bulletin decision is the authoritative PICK observation."""
    captured = parse_dt(bet.get("odds_captured_at") or bet.get("decision_timestamp"))
    if captured is None or bet.get("odd") is None:
        return None
    decision = bet.get("decision_packet", {}).get("decision", {})
    return {
        "observation_id": decision.get("pick_observation_id"),
        "odd": bet.get("odd"),
        "opposite_odd": bet.get("opposite_odd"),
        "captured_at": captured.isoformat(),
        "snapshot_type": "ENTRY",
        "bookmaker_id": bet.get("bookmaker_id"),
        "bookmaker": bet.get("bookmaker"),
        "selection": bet.get("selection") or bet.get("market"),
    }


def true_closing(observations: list[dict[str, Any]], kickoff: datetime | None, pick_at: datetime | None) -> dict[str, Any] | None:
    """CLOSING is the last persisted observation before kickoff, after the pick."""
    if kickoff is None:
        return None
    candidates: list[dict[str, Any]] = []
    for row in observations:
        captured = parse_dt(row.get("odds_captured_at"))
        if captured is None or captured > kickoff:
            continue
        if pick_at is not None and captured <= pick_at:
            continue
        candidates.append(row)
    candidates.sort(key=lambda row: parse_dt(row.get("odds_captured_at")) or datetime.min.replace(tzinfo=UTC))
    return candidates[-1] if candidates else None


def current_after_pick(observations: list[dict[str, Any]], now: datetime, pick_at: datetime | None) -> dict[str, Any] | None:
    """CURRENT must be a real post-PICK persisted observation; never reuse a pre-PICK quote."""
    if pick_at is None:
        return None
    candidates: list[dict[str, Any]] = []
    for row in observations:
        captured = parse_dt(row.get("odds_captured_at"))
        if captured is None or captured <= pick_at or captured > now:
            continue
        candidates.append(row)
    candidates.sort(key=lambda row: parse_dt(row.get("odds_captured_at")) or datetime.min.replace(tzinfo=UTC))
    return candidates[-1] if candidates else None


def enrich(bet: dict[str, Any], now: datetime) -> dict[str, Any]:
    try:
        fixture_id = int(bet["event_id"])
        market = str(bet["market"])
        bookmaker_id = int(bet["bookmaker_id"])
    except (KeyError, TypeError, ValueError):
        fixture_id, market, bookmaker_id = None, "", None

    pick_at = parse_dt(bet.get("odds_captured_at") or bet.get("created_at"))
    kickoff = parse_dt(bet.get("kickoff"))
    selection = str(bet.get("selection") or market)
    observations = (
        observations_for(
            SNAPSHOTS,
            fixture_id=fixture_id,
            market=market,
            bookmaker_id=bookmaker_id,
            selection=selection,
        )
        if fixture_id is not None and bookmaker_id is not None
        else []
    )

    contract = (
        lifecycle_contract(
            observations,
            pick_at=pick_at,
            kickoff=kickoff,
            build_at=now,
        )
        if pick_at is not None
        else {"first_seen": None, "pick": None, "live": None, "closing": None, "closing_recovered": False, "clv_odds_pct": None, "clv_status": "NOT_COMPUTABLE", "timeline": []}
    )

    pick = bulletin_pick(bet) or compact_observation(contract.get("pick"))
    current_row = current_after_pick(observations, now, pick_at) if str(bet.get("status", "PENDING")).upper() == "PENDING" else None
    current = compact_observation(current_row)
    closing_row = true_closing(observations, kickoff, pick_at)
    closing = compact_observation(closing_row) or compact_observation(contract.get("closing"))
    clv = clv_from_odds(pick.get("odd") if pick else None, closing.get("odd") if closing else None)

    active = str(bet.get("status", "PENDING")).upper() == "PENDING"
    current_at = parse_dt(current.get("captured_at")) if current else None
    current_state = (
        "FRESH" if active and current_at and (now - current_at).total_seconds() / 60 <= 15
        else "STALE" if active and current
        else "WAITING_FOR_POST_PICK"
    )

    item = dict(bet)
    item["production_lifecycle"] = {
        "schema_version": contract.get("schema_version", 2),
        "first_seen": compact_observation(contract.get("first_seen")),
        "pick": pick,
        "current": current,
        "live": current,
        "closing": closing,
        "first_seen_observation_id": contract.get("first_seen_observation_id"),
        "pick_observation_id": pick.get("observation_id") if pick else None,
        "current_observation_id": current.get("observation_id") if current else None,
        "live_observation_id": current.get("observation_id") if current else None,
        "closing_observation_id": closing.get("observation_id") if closing else None,
        "current_captured_at": current.get("captured_at") if current else None,
        "live_captured_at": current.get("captured_at") if current else None,
        "live_state": current_state,
        "live_age_minutes": round((now - current_at).total_seconds() / 60.0, 3) if active and current_at else None,
        "current_age_minutes": round((now - current_at).total_seconds() / 60.0, 3) if active and current_at else None,
        "closing_recovered": bool(closing and str(closing.get("snapshot_type")) not in {"T5", "CLOSING"}),
        "closing_snapshot_type": closing.get("snapshot_type") if closing else None,
        "clv_odds_pct": clv,
        "clv_status": "COMPUTABLE" if pick and closing else "NOT_COMPUTABLE",
        "coverage": "FULLY_AUDITABLE" if contract.get("first_seen") and pick and closing else "PARTIAL",
        "timeline": contract.get("timeline", []),
    }
    return item


def main() -> int:
    now = datetime.now(UTC)
    bets = load_json(BETS, [])
    bets = bets if isinstance(bets, list) else []
    enriched = [enrich(b, now) for b in bets if isinstance(b, dict)]
    active = [b for b in enriched if str(b.get("status", "PENDING")).upper() == "PENDING"]
    history = [b for b in enriched if str(b.get("status", "PENDING")).upper() != "PENDING"]
    history.sort(key=lambda b: parse_dt(b.get("settled_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
    meta = load_json(ROOT / "ledger_meta.json", {})
    metrics = load_json(METRICS, {})
    snapshots = load_jsonl(SNAPSHOTS)
    run_at = parse_dt(metrics.get("timestamp"))
    requests_this_run = int(metrics.get("api_requests_used_this_run") or 0)
    last_snapshot = max((parse_dt(r.get("odds_captured_at")) for r in snapshots), default=None)
    run_age = max(0.0, (now - run_at).total_seconds() / 60.0) if run_at else None
    run_state = "FRESH" if run_age is not None and run_age <= 15 and requests_this_run > 0 else "RUN_NO_API" if run_age is not None and run_age <= 15 else "STALE" if run_age is not None else "NO_RUN"
    output = {
        "schema_version": 7,
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
        "rules": {
            "first_seen": "earliest valid persisted observation for exact fixture/market/bookmaker/selection",
            "pick": "exact Daily Bulletin odds at the production decision timestamp",
            "current": "latest valid persisted observation strictly after PICK and before kickoff; ACTIVE/PENDING only",
            "closing": "last valid persisted odds observation before kickoff, after the pick",
            "clv": "Pick odd / Closing odd - 1; null when Pick or Closing is unavailable",
            "missing_data": "null; dashboard renders as —",
        },
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
