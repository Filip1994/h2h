from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.odds_lifecycle import clv_from_odds, lifecycle_contract, observations_for

DASHBOARD = ROOT / "production_dashboard.json"
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"


def dt(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def compact(row):
    if not row:
        return None
    return {
        "observation_id": row.get("observation_id"),
        "odd": row.get("odd"),
        "selection_odd": row.get("odd"),
        "opposite_odd": row.get("opposite_odd"),
        "selected_selection": row.get("selection"),
        "captured_at": row.get("odds_captured_at"),
        "snapshot_type": row.get("snapshot_type"),
        "bookmaker_id": row.get("bookmaker_id"),
        "bookmaker": row.get("bookmaker"),
        "selection": row.get("selection"),
        "market": row.get("market"),
        "quote_semantics": "odd = selected_selection; opposite_odd = opposite_selection",
    }


def patch_bet(bet: dict, now: datetime) -> None:
    try:
        fixture_id = int(bet["event_id"])
        market = str(bet["market"])
        bookmaker_id = int(bet["bookmaker_id"])
        pick_at = dt(bet.get("odds_captured_at") or bet.get("created_at"))
        kickoff = dt(bet.get("kickoff"))
        if pick_at is None or kickoff is None:
            return
    except (KeyError, TypeError, ValueError):
        return

    observations = observations_for(
        SNAPSHOTS,
        fixture_id=fixture_id,
        market=market,
        bookmaker_id=bookmaker_id,
        selection=str(bet.get("selection") or market),
    )
    contract = lifecycle_contract(observations, pick_at=pick_at, kickoff=kickoff, build_at=now)
    closing = compact(contract.get("closing"))
    lifecycle = bet.get("production_lifecycle")
    if not isinstance(lifecycle, dict):
        lifecycle = {}
        bet["production_lifecycle"] = lifecycle

    lifecycle["closing"] = closing
    lifecycle["closing_observation_id"] = closing.get("observation_id") if closing else None
    lifecycle["closing_captured_at"] = closing.get("captured_at") if closing else None
    lifecycle["closing_snapshot_type"] = closing.get("snapshot_type") if closing else None
    lifecycle["closing_target"] = "T-15m (10-20m capture window)"
    lifecycle["closing_unavailable_reason"] = None if closing else "NO_VALID_T15_CLOSE"
    lifecycle["clv_odds_pct"] = clv_from_odds(
        lifecycle.get("pick", {}).get("odd") if lifecycle.get("pick") else bet.get("odd"),
        closing.get("odd") if closing else None,
    )
    lifecycle["clv_status"] = "COMPUTABLE" if lifecycle["clv_odds_pct"] is not None else "NOT_COMPUTABLE"
    lifecycle["coverage"] = "FULLY_AUDITABLE" if lifecycle.get("first_seen") and lifecycle.get("pick") and closing else "PARTIAL"


def main() -> int:
    if not DASHBOARD.exists():
        return 0
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    for bucket in ("active", "history"):
        rows = dashboard.get(bucket, [])
        if isinstance(rows, list):
            for bet in rows:
                if isinstance(bet, dict):
                    patch_bet(bet, now)
    dashboard["closing_policy"] = {
        "definition": "nearest exact-bookmaker observation to T-15m",
        "capture_window": "T-10m to T-20m",
        "fallback": "none",
    }
    DASHBOARD.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"closing_policy": dashboard["closing_policy"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
