from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TERMINAL_RESOLUTION_STATUSES = {"SETTLED", "VOID", "SKIPPED", "CANCELLED"}
STALE_RESOLUTION_STATUS = "STALE_UNRESOLVED"
ACTIVE_RESOLUTION_STATUS = "ACTIVE_UNRESOLVED"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _parse(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except ValueError:
        return None


def _resolution_status(item: dict) -> str:
    explicit = str(item.get("resolution_status") or "").upper()
    if explicit == STALE_RESOLUTION_STATUS:
        return STALE_RESOLUTION_STATUS
    if explicit in TERMINAL_RESOLUTION_STATUSES:
        return explicit
    return ACTIVE_RESOLUTION_STATUS


def check_settlement_health(
    root: Path, now: datetime, max_age_minutes: int = 30
) -> dict:
    cutoff = now - timedelta(minutes=max_age_minutes)
    active_unresolved: list[dict] = []
    stale_unresolved: list[dict] = []
    for source_name in ("bets.json", "intraday_alerts.json"):
        for item in _load(root / source_name):
            if str(item.get("status", "")).upper() != "PENDING":
                continue
            kickoff = _parse(item.get("kickoff"))
            if kickoff is None or kickoff + timedelta(minutes=90) > cutoff:
                continue
            resolution_status = _resolution_status(item)
            record = {
                "source": source_name,
                "id": item.get("id"),
                "event_id": item.get("event_id"),
                "match": item.get("match"),
                "kickoff": item.get("kickoff"),
                "eligible_at": (kickoff + timedelta(minutes=90)).isoformat(),
                "original_status": item.get("status"),
                "resolution_status": resolution_status,
                "last_settlement_attempt_at": item.get("last_settlement_attempt_at"),
                "settlement_failure_reason": item.get("settlement_failure_reason"),
                "classified_at": item.get("resolution_classified_at"),
            }
            if resolution_status == STALE_RESOLUTION_STATUS:
                stale_unresolved.append(record)
            else:
                active_unresolved.append(record)
    return {
        "checked_at": now.isoformat(),
        "max_age_minutes": max_age_minutes,
        "stale_pending_count": len(active_unresolved) + len(stale_unresolved),
        "active_unresolved_count": len(active_unresolved),
        "stale_unresolved_count": len(stale_unresolved),
        "status": "FAIL" if active_unresolved else "OK_WITH_WARNING" if stale_unresolved else "OK",
        "active_unresolved": active_unresolved,
        "stale_unresolved": stale_unresolved,
        "stale_pending": [*active_unresolved, *stale_unresolved],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect active and stale pending QuantBet settlements"
    )
    parser.add_argument("--max-age-minutes", type=int, default=30)
    args = parser.parse_args()
    report = check_settlement_health(ROOT, datetime.now(UTC), args.max_age_minutes)
    (ROOT / "settlement_health.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] == "FAIL":
        print(
            f"ERROR: {report['active_unresolved_count']} active settlement(s) remain PENDING "
            "after the health threshold."
        )
        for item in report["active_unresolved"]:
            print(
                f" - {item['source']} {item['id']} event={item['event_id']} "
                f"kickoff={item['kickoff']} resolution={item['resolution_status']}"
            )
        return 1
    if report["status"] == "OK_WITH_WARNING":
        print(
            f"Settlement health: OK_WITH_WARNING; "
            f"{report['stale_unresolved_count']} stale historical settlement(s) remain auditably unresolved."
        )
        for item in report["stale_unresolved"]:
            print(
                f" - {item['source']} {item['id']} event={item['event_id']} "
                f"kickoff={item['kickoff']} resolution={item['resolution_status']}"
            )
        return 0
    print("Settlement health: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
