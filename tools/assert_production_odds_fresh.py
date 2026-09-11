from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "production_dashboard.json"
MAX_AGE_MINUTES = 10


def parse_dt(value: object) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def main() -> int:
    if not DASHBOARD.exists():
        print("PRODUCTION_ODDS_HEALTH=FAIL reason=NO_DASHBOARD")
        return 1
    try:
        dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"PRODUCTION_ODDS_HEALTH=FAIL reason=INVALID_DASHBOARD error={exc}")
        return 1

    now = datetime.now(UTC)
    monitoring = dashboard.get("monitoring", {})
    active = dashboard.get("active", [])
    failures: list[str] = []

    collector_at = parse_dt(monitoring.get("last_collector_run_at"))
    if collector_at is None:
        failures.append("NO_COLLECTOR_RUN")
    else:
        age = (now - collector_at).total_seconds() / 60.0
        if age > MAX_AGE_MINUTES:
            failures.append(f"COLLECTOR_STALE:{age:.1f}m")

    for bet in active if isinstance(active, list) else []:
        lifecycle = bet.get("production_lifecycle", {}) if isinstance(bet, dict) else {}
        current_at = parse_dt(lifecycle.get("current_captured_at"))
        kickoff = parse_dt(bet.get("kickoff")) if isinstance(bet, dict) else None
        if kickoff is not None and kickoff <= now:
            continue
        if current_at is None:
            failures.append(f"NO_CURRENT:{bet.get('id', 'UNKNOWN')}")
            continue
        age = (now - current_at).total_seconds() / 60.0
        if age > MAX_AGE_MINUTES:
            failures.append(f"CURRENT_STALE:{bet.get('id', 'UNKNOWN')}:{age:.1f}m")

    if failures:
        print("PRODUCTION_ODDS_HEALTH=FAIL " + " ".join(failures))
        return 1

    print(f"PRODUCTION_ODDS_HEALTH=PASS active={len(active) if isinstance(active, list) else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
