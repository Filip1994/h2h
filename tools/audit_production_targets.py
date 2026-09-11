from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BETS = ROOT / "bets.json"
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
DASHBOARD = ROOT / "production_dashboard.json"
OUT = ROOT / "production_quote_health.json"
SLA_MINUTES = 10.0


def parse_dt(value: Any) -> datetime | None:
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


def main() -> int:
    now = datetime.now(UTC)
    bets = load_json(BETS, [])
    snapshots = load_jsonl(SNAPSHOTS)
    active = [
        b for b in bets if isinstance(b, dict) and str(b.get("status", "PENDING")).upper() == "PENDING"
    ]
    targets: list[dict[str, Any]] = []

    for bet in active:
        try:
            fixture_id = int(bet["event_id"])
            bookmaker_id = int(bet["bookmaker_id"])
            market = str(bet["market"])
            selection = str(bet.get("selection") or market)
            kickoff = parse_dt(bet.get("kickoff"))
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff is not None and kickoff <= now:
            continue

        exact = []
        for row in snapshots:
            try:
                matches = (
                    int(row.get("fixture_id")) == fixture_id
                    and int(row.get("bookmaker_id")) == bookmaker_id
                    and str(row.get("market")) == market
                    and str(row.get("selection")) == selection
                )
            except (TypeError, ValueError):
                matches = False
            if matches:
                captured = parse_dt(row.get("odds_captured_at"))
                if captured is not None and (kickoff is None or captured < kickoff):
                    exact.append((captured, row))

        exact.sort(key=lambda item: item[0])
        latest = exact[-1][1] if exact else None
        captured_at = parse_dt(latest.get("odds_captured_at")) if latest else None
        age = ((now - captured_at).total_seconds() / 60.0) if captured_at else None
        if latest is None:
            status = "MISSING_TARGET_QUOTE"
            reason = "NO_EXACT_FIXTURE_BOOKMAKER_MARKET_SELECTION_OBSERVATION"
        elif age is not None and age <= SLA_MINUTES:
            status = "FRESH"
            reason = None
        else:
            status = "STALE_TARGET_QUOTE"
            reason = "EXACT_TARGET_QUOTE_OLDER_THAN_SLA"

        targets.append(
            {
                "bet_id": bet.get("id"),
                "fixture_id": fixture_id,
                "match": bet.get("match"),
                "kickoff": kickoff.isoformat() if kickoff else None,
                "market": market,
                "selection": selection,
                "bookmaker_id": bookmaker_id,
                "bookmaker": bet.get("bookmaker"),
                "pick_odd": bet.get("odd"),
                "latest_odd": latest.get("odd") if latest else None,
                "latest_captured_at": captured_at.isoformat() if captured_at else None,
                "age_minutes": round(age, 3) if age is not None else None,
                "status": status,
                "reason": reason,
                "observation_id": latest.get("observation_id") if latest else None,
            }
        )

    counts = {
        "active": len(targets),
        "fresh": sum(t["status"] == "FRESH" for t in targets),
        "stale": sum(t["status"] == "STALE_TARGET_QUOTE" for t in targets),
        "missing": sum(t["status"] == "MISSING_TARGET_QUOTE" for t in targets),
    }
    overall = "FRESH" if targets and counts["fresh"] == counts["active"] else "DEGRADED" if targets else "NO_ACTIVE_TARGETS"
    health = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "sla_minutes": SLA_MINUTES,
        "overall": overall,
        "counts": counts,
        "targets": targets,
        "semantics": "Target health is exact fixture + bookmaker + market + selection. Missing/stale target data is degraded state, never fabricated data and never a reason to discard unrelated collector observations.",
    }
    OUT.write_text(json.dumps(health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dashboard = load_json(DASHBOARD, {})
    if isinstance(dashboard, dict):
        monitoring = dashboard.setdefault("monitoring", {})
        monitoring["production_quote_health"] = health
        dashboard["generated_at"] = now.isoformat()
        DASHBOARD.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"overall": overall, "counts": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
