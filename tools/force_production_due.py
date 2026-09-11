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

    for bet in bets if isinstance(bets, list) else []:
        if not isinstance(bet, dict) or str(bet.get("status", "PENDING")).upper() != "PENDING":
            continue
        try:
            fixture_id = int(bet["event_id"])
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
        forced.append(fixture_id)

    state["updated_at"] = now.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"forced_production_fixtures": sorted(set(forced)), "timestamp": now.isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
