from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "intraday_health.json"


def _load(name: str):
    path = ROOT / name
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-status", required=True, choices=("success", "failure"))
    args = parser.parse_args()
    now = datetime.now(UTC).isoformat()
    strong = _load("strong_signals.json")
    near = _load("near_misses.json")
    alerts = _load("intraday_alerts.json")
    if args.run_status == "failure":
        status = "ERROR"
    else:
        active = [
            item
            for item in [*strong, *near, *alerts]
            if str(item.get("status", "PENDING")).upper() == "PENDING"
        ]
        status = "RUNNING" if active else "NO SIGNALS"
    payload = {
        "status": status,
        "last_run_at": now,
        "workflow": "intraday.yml",
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "workflow_sha": os.environ.get("GITHUB_SHA", ""),
        "timezone": "Europe/Belgrade",
        "strong_signal_count": len(strong),
        "near_miss_count": len(near),
        "intraday_alert_count": len(alerts),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Intraday health: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
