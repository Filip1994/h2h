from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FRESHNESS_MINUTES = 10


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _active(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if str(record.get("status", "")).upper() in {"PENDING", "OPEN", "ACTIVE", "WATCHING"}
    ]


def build(root: Path) -> dict[str, Any]:
    targets: dict[tuple[int, str, int], dict[str, Any]] = {}
    for source, path in (("PRODUCTION", root / "bets.json"), ("STRONG_SIGNAL", root / "strong_signals.json")):
        for record in _active(_load_json(path, [])):
            fixture_id = record.get("event_id", record.get("fixture_id"))
            market = record.get("market")
            bookmaker_id = record.get("bookmaker_id")
            if fixture_id is None or not market or bookmaker_id is None:
                continue
            targets[(int(fixture_id), str(market), int(bookmaker_id))] = {
                "source": source,
                "fixture_id": int(fixture_id),
                "market": str(market),
                "selection": str(record.get("selection") or market),
                "bookmaker_id": int(bookmaker_id),
                "bookmaker_name": record.get("bookmaker") or record.get("bookmaker_name"),
            }

    latest: dict[tuple[int, str, int], dict[str, Any]] = {}
    snapshot_path = root / "data" / "market_timing_snapshots.jsonl"
    try:
        lines = snapshot_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    now = datetime.now(UTC)
    for line in lines:
        try:
            row = json.loads(line)
            key = (int(row["fixture_id"]), str(row["market"]), int(row["bookmaker_id"]))
            if key not in targets:
                continue
            observed = datetime.fromisoformat(str(row["captured_at"])).astimezone(UTC)
            kickoff = datetime.fromisoformat(str(row["kickoff"])).astimezone(UTC)
            if observed >= kickoff:
                continue
            if key not in latest or observed > latest[key]["_observed"]:
                latest[key] = {**row, "_observed": observed}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue

    output = []
    for key, target in sorted(targets.items()):
        row = latest.get(key)
        if row is None:
            output.append(
                {
                    **target,
                    "current_odds": None,
                    "current_observed_at": None,
                    "current_observation_id": None,
                    "current_freshness_state": "UNAVAILABLE",
                }
            )
            continue
        age = max(0.0, (now - row["_observed"]).total_seconds() / 60.0)
        kickoff = datetime.fromisoformat(str(row["kickoff"])).astimezone(UTC)
        state = "CLOSED" if now >= kickoff else ("LIVE" if age <= FRESHNESS_MINUTES else "STALE")
        output.append(
            {
                **target,
                "bookmaker_name": row.get("bookmaker") or target.get("bookmaker_name"),
                "current_odds": row.get("odd"),
                "current_observed_at": row.get("captured_at"),
                "current_observation_id": row.get("observation_id"),
                "current_observation_type": row.get("signal_state") or "OBSERVED",
                "current_freshness_state": state,
            }
        )
    return {"generated_at": now.isoformat(), "freshness_window_minutes": FRESHNESS_MINUTES, "items": output}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    payload = build(args.root)
    (args.root / "current_odds.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"published current odds for {len(payload['items'])} active records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
