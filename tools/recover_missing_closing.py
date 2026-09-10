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

from quantbot.odds_lifecycle import lifecycle_contract
from quantbot.odds_lifecycle import observations_for


def _parse(value: Any) -> datetime:
    return datetime.fromisoformat(str(value)).astimezone(UTC)


def _clv(pick: Any, closing: Any) -> float | None:
    try:
        pick_f = float(pick)
        close_f = float(closing)
    except (TypeError, ValueError):
        return None
    if pick_f <= 1 or close_f <= 1:
        return None
    return round((pick_f / close_f) - 1.0, 6)


def _recover_row(row: dict[str, Any], observations_path: Path) -> bool:
    if row.get("closing_odd") is not None:
        return False
    try:
        pick_at = _parse(row["odds_captured_at"])
        kickoff = _parse(row["kickoff"])
        observations = observations_for(
            observations_path,
            fixture_id=int(row["event_id"]),
            market=str(row["market"]),
            bookmaker_id=int(row["bookmaker_id"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    contract = lifecycle_contract(observations, pick_at=pick_at, kickoff=kickoff)
    closing = contract.get("closing")
    if not closing or not contract.get("closing_recovered"):
        return False
    row["closing_odd"] = closing.get("odd")
    row["closing_odds_captured_at"] = closing.get("odds_captured_at")
    row["closing_snapshot_id"] = closing.get("observation_id")
    row["closing_coverage"] = "RECOVERED_PRE_KICKOFF"
    row["closing_recovery"] = True
    row["closing_recovery_snapshot_type"] = closing.get("snapshot_type")
    row["clv_odds_pct"] = _clv(row.get("odd"), closing.get("odd"))
    row["clv_status"] = "COMPUTABLE" if row["clv_odds_pct"] is not None else "NOT_COMPUTABLE"
    row["lifecycle_coverage"] = (
        "FULLY_AUDITABLE"
        if row.get("opening_odd") is not None and row.get("entry_snapshot_id") and row.get("closing_odd") is not None
        else "PARTIAL"
    )
    return True


def recover(root: Path = ROOT) -> dict[str, int]:
    observations_path = root / "data" / "odds_snapshots.jsonl"
    recovered_bets = 0
    recovered_alerts = 0

    bets_path = root / "bets.json"
    if bets_path.exists():
        bets = json.loads(bets_path.read_text(encoding="utf-8"))
        changed = False
        for row in bets if isinstance(bets, list) else []:
            if isinstance(row, dict) and _recover_row(row, observations_path):
                recovered_bets += 1
                changed = True
        if changed:
            bets_path.write_text(json.dumps(bets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    alerts_path = root / "intraday_alerts.json"
    if alerts_path.exists():
        alerts = json.loads(alerts_path.read_text(encoding="utf-8"))
        changed = False
        for row in alerts if isinstance(alerts, list) else []:
            if isinstance(row, dict) and _recover_row(row, observations_path):
                recovered_alerts += 1
                changed = True
        if changed:
            alerts_path.write_text(json.dumps(alerts[-1000:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"bets_recovered": recovered_bets, "alerts_recovered": recovered_alerts}


if __name__ == "__main__":
    print(json.dumps(recover(), ensure_ascii=False))
