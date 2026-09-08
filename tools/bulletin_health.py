from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MARKER_PATH = ROOT / "bulletin_health.json"
BUSINESS_TZ = ZoneInfo("Europe/Belgrade")


def _load_marker(path: Path = MARKER_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def business_date(now: datetime) -> str:
    return now.astimezone(BUSINESS_TZ).date().isoformat()


def is_successful_for_today(marker: dict, now: datetime) -> bool:
    return (
        marker.get("status") == "SUCCESS"
        and marker.get("business_date") == business_date(now)
        and marker.get("generation_status") == "SUCCESS"
        and marker.get("commit_status") == "SUCCESS"
        and marker.get("send_status") == "SUCCESS"
        and bool(marker.get("completed_at"))
    )


def build_success_marker(
    now: datetime,
    *,
    generation_started_at: str,
    generation_completed_at: str,
) -> dict:
    run_id = __import__("os").environ.get("GITHUB_RUN_ID", "")
    run_attempt = __import__("os").environ.get("GITHUB_RUN_ATTEMPT", "")
    sha = __import__("os").environ.get("GITHUB_SHA", "")
    return {
        "business_date": business_date(now),
        "status": "SUCCESS",
        "generation_status": "SUCCESS",
        "commit_status": "SUCCESS",
        "send_status": "SUCCESS",
        "generation_started_at": generation_started_at,
        "generation_completed_at": generation_completed_at,
        "completed_at": now.astimezone(UTC).isoformat(),
        "workflow": "daily.yml",
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "workflow_sha": sha,
        "timezone": "Europe/Belgrade",
    }


def write_success_marker(marker: dict, path: Path = MARKER_PATH) -> None:
    path.write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QuantBet daily bulletin health marker"
    )
    parser.add_argument("--guard", action="store_true")
    parser.add_argument("--write-success", action="store_true")
    parser.add_argument("--generation-started-at")
    parser.add_argument("--generation-completed-at")
    args = parser.parse_args()
    now = datetime.now(BUSINESS_TZ)
    marker = _load_marker()

    if args.guard:
        healthy = is_successful_for_today(marker, now)
        print("BULLETIN_HEALTH=SUCCESS" if healthy else "BULLETIN_HEALTH=MISSING")
        print(f"BUSINESS_DATE={business_date(now)}")
        if healthy:
            return 0
        return 1

    if args.write_success:
        if not args.generation_started_at or not args.generation_completed_at:
            parser.error("--write-success requires generation timestamps")
        write_success_marker(
            build_success_marker(
                now,
                generation_started_at=args.generation_started_at,
                generation_completed_at=args.generation_completed_at,
            )
        )
        print(f"Bulletin health marker: SUCCESS ({business_date(now)})")
        return 0

    parser.error("choose --guard or --write-success")
    return 2


if __name__ == "__main__":
    sys.exit(main())
