from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


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


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def audit(root: Path = ROOT) -> dict:
    metrics = _load_json(root / "odds_collection_metrics.json")
    state = _load_json(root / "odds_collection_state.json")
    coverage = _load_jsonl(root / "data" / "odds_collection_coverage.jsonl")

    errors: list[str] = []
    required_metrics = {
        "timestamp", "eligible_fixtures", "queried_fixtures", "observations_captured",
        "api_requests_used_this_run", "daily_budget_remaining", "provider_availability_by_ttk",
        "actual_scan_timestamps",
    }
    missing = sorted(required_metrics - metrics.keys())
    if missing:
        errors.append("METRICS_MISSING_FIELDS:" + ",".join(missing))

    run_at = _parse(metrics.get("timestamp"))
    if run_at is None:
        errors.append("INVALID_RUN_TIMESTAMP")

    eligible = int(metrics.get("eligible_fixtures") or 0)
    queried = int(metrics.get("queried_fixtures") or 0)
    requests = int(metrics.get("api_requests_used_this_run") or 0)
    observations = int(metrics.get("observations_captured") or 0)
    if min(eligible, queried, requests, observations) < 0:
        errors.append("NEGATIVE_RUNTIME_COUNTER")
    if queried > eligible:
        errors.append("QUERIED_EXCEEDS_ELIGIBLE")
    if eligible > 0 and requests == 0:
        errors.append("ELIGIBLE_UNIVERSE_WITHOUT_PROVIDER_REQUEST")
    if eligible > 0 and queried == 0 and not int(metrics.get("budget_exhausted") or 0):
        errors.append("ELIGIBLE_UNIVERSE_NOT_SCANNED")

    scan_timestamps = metrics.get("actual_scan_timestamps")
    if not isinstance(scan_timestamps, list):
        errors.append("INVALID_SCAN_TIMESTAMP_LIST")
    elif queried > 0 and not scan_timestamps:
        errors.append("QUERIED_WITHOUT_SCAN_TIMESTAMP")

    state_fixtures = state.get("fixtures")
    if not isinstance(state_fixtures, dict):
        errors.append("INVALID_STATE_FIXTURES")
        state_fixtures = {}
    if eligible > 0 and len(state_fixtures) < eligible:
        errors.append("STATE_FIXTURE_COUNT_BELOW_ELIGIBLE")

    current_fixtures = []
    if run_at is not None:
        horizon = run_at + timedelta(hours=72, minutes=5)
        for fixture_id, item in state_fixtures.items():
            if not isinstance(item, dict):
                continue
            if _parse(item.get("last_seen_at")) != run_at:
                continue
            current_fixtures.append(fixture_id)
            kickoff = _parse(item.get("kickoff"))
            if kickoff is None:
                errors.append(f"MISSING_KICKOFF:{fixture_id}")
            elif kickoff <= run_at or kickoff > horizon:
                errors.append(f"FIXTURE_OUTSIDE_72H_WINDOW:{fixture_id}")
    if eligible > 0 and len(current_fixtures) < eligible:
        errors.append("CURRENT_STATE_FIXTURE_COUNT_BELOW_ELIGIBLE")

    run_coverage = [row for row in coverage if _parse(row.get("captured_at")) == run_at] if run_at else []
    if queried > 0 and not run_coverage:
        errors.append("QUERIED_WITHOUT_COVERAGE_EVIDENCE")
    coverage_with_outcome = sum(1 for row in run_coverage if row.get("outcome"))
    if queried > 0 and coverage_with_outcome < queried:
        errors.append("COVERAGE_OUTCOMES_BELOW_QUERIED")

    status = "PASS" if not errors else "FAIL"
    payload = {
        "schema_version": 1,
        "audited_at": datetime.now(UTC).isoformat(),
        "run_timestamp": metrics.get("timestamp"),
        "status": status,
        "eligible_fixtures": eligible,
        "queried_fixtures": queried,
        "api_requests_used_this_run": requests,
        "observations_captured": observations,
        "coverage_rows_for_run": len(run_coverage),
        "provider_availability_by_ttk": metrics.get("provider_availability_by_ttk", {}),
        "errors": errors,
        "evidence": {
            "next_72h_universe_checked": not any(
                error.startswith(("MISSING_KICKOFF:", "FIXTURE_OUTSIDE_72H_WINDOW:")) for error in errors
            ),
            "provider_scan_proven": queried > 0 and requests > 0,
            "coverage_outcomes_proven": coverage_with_outcome >= queried,
        },
    }
    (root / "odds_collection_runtime_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise SystemExit("Exhaustive odds runtime audit FAILED: " + "; ".join(errors))
    return payload


if __name__ == "__main__":
    audit()
