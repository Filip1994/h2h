from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATUSES = {"WIN", "LOSS", "SKIPPED", "VOID", "REVIEW"}
ACTIVE_STATUS = "PENDING"
KNOWN_STATUSES = TERMINAL_STATUSES | {ACTIVE_STATUS}


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"MISSING_CANONICAL_DATA:{path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"INVALID_CANONICAL_DATA:{path.name}") from exc
    if not isinstance(payload, list) or any(
        not isinstance(item, dict) for item in payload
    ):
        raise RuntimeError(f"INVALID_CANONICAL_DATA:{path.name}")
    return payload


def _parse(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def inspect_source(
    source: str,
    rows: list[dict[str, Any]],
    now: datetime,
    stale_minutes: int,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    cutoff = now - timedelta(minutes=stale_minutes)

    for row in rows:
        row_id = str(row.get("id") or "")
        status = str(row.get("status") or "").upper()
        event_id = row.get("event_id")
        if not row_id:
            errors.append(
                {"source": source, "error": "MISSING_ID", "event_id": event_id}
            )
        elif row_id in seen_ids:
            errors.append(
                {"source": source, "error": "DUPLICATE_ID", "id": row_id}
            )
        seen_ids.add(row_id)

        if status not in KNOWN_STATUSES:
            errors.append(
                {
                    "source": source,
                    "error": "UNKNOWN_STATUS",
                    "id": row_id,
                    "status": status,
                }
            )
            continue

        if event_id is None:
            errors.append(
                {"source": source, "error": "MISSING_EVENT_ID", "id": row_id}
            )

        kickoff = _parse(row.get("kickoff"))
        if status == ACTIVE_STATUS:
            active.append(
                {
                    "source": source,
                    "id": row_id,
                    "event_id": event_id,
                    "match": row.get("match"),
                    "kickoff": row.get("kickoff"),
                }
            )
            if kickoff is None:
                errors.append(
                    {
                        "source": source,
                        "error": "ACTIVE_MISSING_VALID_KICKOFF",
                        "id": row_id,
                    }
                )
            elif kickoff + timedelta(minutes=90) <= cutoff:
                errors.append(
                    {
                        "source": source,
                        "error": "STALE_ACTIVE",
                        "id": row_id,
                        "event_id": event_id,
                        "match": row.get("match"),
                        "kickoff": row.get("kickoff"),
                        "eligible_at": (kickoff + timedelta(minutes=90)).isoformat(),
                    }
                )
        elif (
            status in TERMINAL_STATUSES
            and not row.get("settled_at")
            and status != "SKIPPED"
        ):
            errors.append(
                {
                    "source": source,
                    "error": "TERMINAL_MISSING_SETTLED_AT",
                    "id": row_id,
                    "status": status,
                }
            )

    return {
        "records": len(rows),
        "active_count": len(active),
        "active": active,
        "errors": errors,
    }


def check_system_health(
    root: Path = ROOT,
    now: datetime | None = None,
    stale_minutes: int = 30,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    sources = {
        "bets.json": _load(root / "bets.json"),
        "intraday_alerts.json": _load(root / "intraday_alerts.json"),
    }
    inspections = {
        name: inspect_source(name, rows, now, stale_minutes)
        for name, rows in sources.items()
    }
    errors = [error for report in inspections.values() for error in report["errors"]]
    active_count = sum(report["active_count"] for report in inspections.values())
    return {
        "schema_version": 1,
        "checked_at": now.isoformat(),
        "stale_minutes": stale_minutes,
        "status": "FAIL" if errors else "OK",
        "production_active_count": inspections["bets.json"]["active_count"],
        "intraday_active_count": inspections["intraday_alerts.json"]["active_count"],
        "active_count": active_count,
        "errors": errors,
        "sources": inspections,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Canonical QuantBet production system health gate"
    )
    parser.add_argument("--stale-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        report = check_system_health(stale_minutes=args.stale_minutes)
    except RuntimeError as exc:
        report = {
            "schema_version": 1,
            "checked_at": datetime.now(UTC).isoformat(),
            "status": "FAIL",
            "production_active_count": None,
            "intraday_active_count": None,
            "active_count": None,
            "errors": [{"error": str(exc)}],
            "sources": {},
        }
    (ROOT / "system_health.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if report["status"] == "FAIL":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(f"System health: OK; active={report['active_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
