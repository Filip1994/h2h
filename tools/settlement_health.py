from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from tools.system_health import check_system_health

ROOT = Path(__file__).resolve().parents[1]


def check_settlement_health(
    root: Path, now: datetime, max_age_minutes: int = 30
) -> dict:
    report = check_system_health(root, now=now, stale_minutes=max_age_minutes)
    stale = [
        error
        for error in report.get("errors", [])
        if error.get("error") == "STALE_ACTIVE"
    ]
    return {
        "checked_at": report["checked_at"],
        "max_age_minutes": max_age_minutes,
        "stale_pending_count": len(stale),
        "active_count": report.get("active_count"),
        "status": report["status"],
        "stale_pending": stale,
        "errors": report.get("errors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect stale or otherwise unsafe QuantBet settlements"
    )
    parser.add_argument("--max-age-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        report = check_settlement_health(ROOT, datetime.now(UTC), args.max_age_minutes)
    except RuntimeError as exc:
        report = {
            "checked_at": datetime.now(UTC).isoformat(),
            "max_age_minutes": args.max_age_minutes,
            "stale_pending_count": 0,
            "active_count": None,
            "status": "FAIL",
            "stale_pending": [],
            "errors": [{"error": str(exc)}],
        }
    (ROOT / "settlement_health.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] == "FAIL":
        print("ERROR: settlement/system health failed closed.")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(f"Settlement health: OK; active={report.get('active_count', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
