from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantbot.odds_lifecycle import lifecycle_contract, observations_for

ROOT = Path(__file__).resolve().parents[1]
BETS = ROOT / "bets.json"
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
OUT = ROOT / "production_dashboard.json"


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
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
    }


def enrich(bet: dict[str, Any], now: datetime) -> dict[str, Any]:
    try:
        fixture_id = int(bet["event_id"])
        market = str(bet["market"])
        bookmaker_id = int(bet["bookmaker_id"])
    except (KeyError, TypeError, ValueError):
        fixture_id = None
        market = ""
        bookmaker_id = None

    pick_at = parse_dt(bet.get("odds_captured_at") or bet.get("created_at"))
    kickoff = parse_dt(bet.get("kickoff"))
    observations = (
        observations_for(
            SNAPSHOTS,
            fixture_id=fixture_id,
            market=market,
            bookmaker_id=bookmaker_id,
        )
        if fixture_id is not None and bookmaker_id is not None
        else []
    )

    contract = (
        lifecycle_contract(observations, pick_at=pick_at, kickoff=kickoff)
        if pick_at is not None
        else {
            "opening": None,
            "pick": None,
            "closing": None,
            "closing_recovered": False,
            "coverage": "UNRECOVERABLE",
            "clv_odds_pct": None,
            "clv_status": "NOT_COMPUTABLE",
        }
    )

    latest = observations[-1] if observations else None
    live_ts = parse_dt(latest.get("odds_captured_at")) if latest else None
    if live_ts is None:
        live_state = "NO_OBSERVATION"
    else:
        age_minutes = max(0.0, (now - live_ts).total_seconds() / 60.0)
        live_state = "FRESH" if age_minutes <= 15 else "STALE"

    item = dict(bet)
    item["production_lifecycle"] = {
        "opening": compact_observation(contract.get("opening")),
        "pick": compact_observation(contract.get("pick"))
        or {
            "odd": bet.get("odd"),
            "captured_at": bet.get("odds_captured_at"),
            "observation_id": bet.get("pick_snapshot_id") or bet.get("pick_observation_id"),
        },
        "live": compact_observation(latest),
        "live_state": live_state,
        "closing": compact_observation(contract.get("closing")),
        "closing_rule": "canonical lifecycle: T-2m_to_T-8m, with latest honest pre-kickoff recovery if exact T5 is missed",
        "closing_recovered": bool(contract.get("closing_recovered")),
        "clv_odds_pct": contract.get("clv_odds_pct"),
        "coverage": "FULL" if contract.get("opening") and contract.get("pick") and contract.get("closing") else "PARTIAL",
    }
    return item


def main() -> int:
    now = datetime.now(UTC)
    bets = load_json(BETS, [])
    if not isinstance(bets, list):
        bets = []
    enriched = [enrich(b, now) for b in bets if isinstance(b, dict)]
    active = [b for b in enriched if str(b.get("status", "PENDING")).upper() == "PENDING"]
    history = [b for b in enriched if str(b.get("status", "PENDING")).upper() != "PENDING"]
    meta = load_json(ROOT / "ledger_meta.json", {})
    output = {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "truth": "data/odds_snapshots.jsonl + bets.json",
        "rules": {
            "opening": "canonical lifecycle: first OPENING/INTERMEDIATE observation for the exact Production fixture/market/bookmaker at or before Pick",
            "live": "latest persisted observation for the exact Production fixture/market/bookmaker",
            "closing": "canonical lifecycle: T-2m to T-8m exact observation; if missed, latest honest INTERMEDIATE/T5/CLOSING observation after Pick and before kickoff",
            "clv": "Pick odd / Closing odd - 1; null when Closing is unavailable",
            "missing_data": "null; dashboard renders as —",
        },
        "initial_bank": meta.get("initial_bank", 50000),
        "active": active,
        "history": history,
        "counts": {"production": len(enriched), "active": len(active), "history": len(history), "snapshots": sum(1 for _ in load_jsonl(SNAPSHOTS))},
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
