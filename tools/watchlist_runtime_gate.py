# fmt: off
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def _load_json(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default
    return value


def _load_run_result(path: Path) -> dict | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_number(payload: dict, *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            return None
    return None


def evaluate(
    run_result: dict,
    predictions: list[dict],
    *,
    now: datetime,
    lookahead_hours: float,
) -> dict:
    scanned = _first_number(run_result, "fixtures_scanned", "scanned")
    api_requests = _first_number(run_result, "api_requests", "request_count")
    if api_requests is None and isinstance(run_result.get("api_usage"), dict):
        api_requests = _first_number(
            run_result["api_usage"], "request_count", "requests"
        )

    eligible: set[int] = set()
    for prediction in predictions:
        try:
            fixture_id = int(prediction["event_id"])
            kickoff = _parse(prediction["kickoff"])
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff is None:
            continue
        seconds = (kickoff - now.astimezone(UTC)).total_seconds()
        if 300 < seconds <= lookahead_hours * 3600:
            eligible.add(fixture_id)

    errors: list[str] = []
    if scanned is None:
        errors.append("WATCHLIST_RESULT_MISSING_FIXTURE_SCAN_COUNT")
    if api_requests is None:
        errors.append("WATCHLIST_RESULT_MISSING_API_REQUEST_COUNT")
    if scanned is not None and eligible and scanned == 0:
        errors.append("ELIGIBLE_FIXTURES_WITH_ZERO_SCANS")
    if api_requests is not None and eligible and api_requests == 0:
        errors.append("ELIGIBLE_FIXTURES_WITH_ZERO_API_REQUESTS")
    if scanned is not None and scanned > 0 and api_requests == 0:
        errors.append("SCANS_REPORTED_WITH_ZERO_API_REQUESTS")

    if errors:
        status = "ERROR"
    elif not eligible:
        status = "NO_ELIGIBLE_FIXTURES"
    else:
        status = "OK"

    return {
        "schema_version": 1,
        "status": status,
        "checked_at": now.astimezone(UTC).isoformat(),
        "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
        "source_sha": os.getenv("GITHUB_SHA"),
        "eligible_fixture_count": len(eligible),
        "fixtures_scanned": scanned,
        "api_requests": api_requests,
        "errors": errors,
        "observation_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed scheduled watchlist runtime gate"
    )
    parser.add_argument("--run-output", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, default=Path("predictions.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("watchlist_runtime_health.json")
    )
    parser.add_argument(
        "--lookahead-hours",
        type=float,
        default=float(os.getenv("INTRADAY_LOOKAHEAD_HOURS", "6")),
    )
    args = parser.parse_args()

    run_result = _load_run_result(args.run_output)
    predictions = _load_json(args.predictions, [])
    if not isinstance(run_result, dict):
        payload = {
            "schema_version": 1,
            "status": "ERROR",
            "checked_at": datetime.now(UTC).isoformat(),
            "errors": ["WATCHLIST_RESULT_NOT_VALID_JSON_OBJECT"],
            "observation_only": True,
        }
        args.output.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return 1
    if not isinstance(predictions, list):
        predictions = []

    payload = evaluate(
        run_result,
        [item for item in predictions if isinstance(item, dict)],
        now=datetime.now(UTC),
        lookahead_hours=args.lookahead_hours,
    )
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 1 if payload["status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
