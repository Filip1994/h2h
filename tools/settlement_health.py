from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def check_settlement_health(
    root: Path, now: datetime, max_age_minutes: int = 30
) -> dict:
    cutoff = now - timedelta(minutes=max_age_minutes)
    stale: list[dict] = []
    for source_name in ("bets.json", "intraday_alerts.json"):
        for item in _load(root / source_name):
            if str(item.get("status", "")).upper() != "PENDING":
                continue
            kickoff = _parse(item.get("kickoff"))
            if kickoff is None or kickoff + timedelta(minutes=90) > cutoff:
                continue
            stale.append(
                {
                    "source": source_name,
                    "id": item.get("id"),
                    "event_id": item.get("event_id"),
                    "match": item.get("match"),
                    "kickoff": item.get("kickoff"),
                    "eligible_at": (kickoff + timedelta(minutes=90)).isoformat(),
                }
            )
    return {
        "checked_at": now.isoformat(),
        "max_age_minutes": max_age_minutes,
        "stale_pending_count": len(stale),
        "status": "FAIL" if stale else "OK",
        "stale_pending": stale,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect stale pending QuantBet settlements"
    )
    parser.add_argument("--max-age-minutes", type=int, default=30)
    args = parser.parse_args()
    report = check_settlement_health(ROOT, datetime.now(UTC), args.max_age_minutes)
    (ROOT / "settlement_health.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] == "FAIL":
        print(
            f"ERROR: {report['stale_pending_count']} settlement(s) remain PENDING "
            "after the health threshold."
        )
        for item in report["stale_pending"]:
            print(
                f" - {item['source']} {item['id']} event={item['event_id']} "
                f"kickoff={item['kickoff']}"
            )
        return 1
    print("Settlement health: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
