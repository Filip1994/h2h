from __future__ import annotations

import json
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
    """Audit freshness without blocking persistence/deployment.

    A stale selected-bookmaker quote is a production degradation, not a reason
    to discard the entire collector run. The dashboard must publish the
    degraded state so a human can see exactly what is stale.
    """
    if not DASHBOARD.exists():
        print("PRODUCTION_ODDS_HEALTH=DEGRADED reason=NO_DASHBOARD")
        return 0

    try:
        dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"PRODUCTION_ODDS_HEALTH=DEGRADED reason=INVALID_DASHBOARD error={exc}")
        return 0

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
        if not isinstance(bet, dict):
            continue
        kickoff = parse_dt(bet.get("kickoff"))
        if kickoff is not None and kickoff <= now:
            continue
        lifecycle = bet.get("production_lifecycle", {})
        current_at = parse_dt(lifecycle.get("current_captured_at"))
        bet_id = bet.get("id", "UNKNOWN")
        if current_at is None:
            failures.append(f"NO_CURRENT:{bet_id}")
            continue
        age = (now - current_at).total_seconds() / 60.0
        if age > MAX_AGE_MINUTES:
            failures.append(f"CURRENT_STALE:{bet_id}:{age:.1f}m")

    if failures:
        print("PRODUCTION_ODDS_HEALTH=DEGRADED " + " ".join(failures))
    else:
        print(f"PRODUCTION_ODDS_HEALTH=PASS active={len(active) if isinstance(active, list) else 0}")

    # Never discard a successful odds collection merely because one target
    # bookmaker is temporarily unavailable. build_production_view.py has
    # already materialized the degraded state for the human-facing dashboard.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
