from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BETS = ROOT / "bets.json"
STATE = ROOT / "odds_collection_state.json"


def parse_dt(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def main() -> int:
    now = datetime.now(UTC)
    bets = json.loads(BETS.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"schema_version": 1, "fixtures": {}}
    fixtures = state.setdefault("fixtures", {})
    forced: list[int] = []
    targets: list[dict] = []

    for bet in bets if isinstance(bets, list) else []:
        if not isinstance(bet, dict) or str(bet.get("status", "PENDING")).upper() != "PENDING":
            continue
        try:
            fixture_id = int(bet["event_id"])
            bookmaker_id = int(bet["bookmaker_id"])
            market = str(bet["market"])
            selection = str(bet.get("selection") or market)
        except (KeyError, TypeError, ValueError):
            continue
        kickoff = parse_dt(bet.get("kickoff"))
        if kickoff is not None and kickoff <= now:
            continue
        item = fixtures.get(str(fixture_id))
        if not isinstance(item, dict):
            item = {"fixture_id": fixture_id}
            fixtures[str(fixture_id)] = item
        item["next_due_at"] = now.isoformat()
        item["production_priority_due"] = True
        target = {
            "bet_id": bet.get("id"),
            "fixture_id": fixture_id,
            "bookmaker_id": bookmaker_id,
            "bookmaker": bet.get("bookmaker"),
            "market": market,
            "selection": selection,
            "pick_odd": bet.get("odd"),
            "kickoff": kickoff.isoformat() if kickoff else None,
            "forced_at": now.isoformat(),
        }
        item["production_target"] = target
        targets.append(target)
        forced.append(fixture_id)

    state["production_targets"] = targets
    state["updated_at"] = now.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"forced_production_fixtures": sorted(set(forced)), "production_targets": targets, "timestamp": now.isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
