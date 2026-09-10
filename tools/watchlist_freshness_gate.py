from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def parse(value):
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def evaluate(predictions, state, now, lookahead_hours=6.0):
    active = {}
    for prediction in predictions:
        try:
            fixture_id = int(prediction["event_id"])
            kickoff = parse(prediction["kickoff"])
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff is None:
            continue
        seconds = (kickoff - now).total_seconds()
        if 300 < seconds <= lookahead_hours * 3600:
            active[fixture_id] = seconds

    stale = []
    for fixture_id, seconds in active.items():
        fixture = state.get(str(fixture_id), {}) if isinstance(state, dict) else {}
        last_scan = parse(fixture.get("last_scan_at"))
        cadence = fixture.get("cadence_seconds", 300)
        try:
            cadence = max(120, int(cadence))
        except (TypeError, ValueError):
            cadence = 300
        max_age = max(900, cadence * 2 + 120)
        age = (now - last_scan).total_seconds() if last_scan else None
        if age is None or age > max_age:
            stale.append({"fixture_id": fixture_id, "seconds_to_kickoff": round(seconds), "last_scan_at": fixture.get("last_scan_at"), "age_seconds": None if age is None else round(age), "max_age_seconds": max_age})
    return {"status": "STALE" if stale else "OK", "checked_at": now.isoformat(), "active_fixture_count": len(active), "stale_fixtures": stale}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, default=Path("predictions.json"))
    parser.add_argument("--state", type=Path, default=Path("intraday_watchlist_state.json"))
    parser.add_argument("--output", type=Path, default=Path("watchlist_freshness.json"))
    args = parser.parse_args()
    predictions = json.loads(args.predictions.read_text(encoding="utf-8")) if args.predictions.exists() else []
    state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
    result = evaluate(predictions if isinstance(predictions, list) else [], state, datetime.now(UTC))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] == "STALE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
