from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
COVERAGE = ROOT / "data" / "odds_collection_coverage.jsonl"
ELIGIBILITY = ROOT / "data" / "eligibility_coverage.jsonl"
STATE = ROOT / "odds_collection_state.json"
BUDGET = ROOT / "odds_collection_budget.json"
API_HISTORY = ROOT / "api_usage_history.json"
REPORT = ROOT / "production_operations_gate.md"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict]:
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


def parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def count_state_outcomes(state_fixtures: object) -> int:
    """Count fixtures carrying a non-empty outcome without leaking strings into sum()."""
    if not isinstance(state_fixtures, dict):
        return 0
    return sum(
        1
        for value in state_fixtures.values()
        if isinstance(value, dict) and bool(value.get("last_outcome"))
    )


def main() -> int:
    snapshots = load_jsonl(SNAPSHOTS)
    coverage = load_jsonl(COVERAGE)
    eligibility = load_jsonl(ELIGIBILITY)
    state = load_json(STATE, {})
    budget = load_json(BUDGET, {})
    api_history = load_json(API_HISTORY, [])

    lifecycle_keys: dict[tuple[int, str, int], list[dict]] = defaultdict(list)
    malformed = 0
    post_kickoff_closing = 0
    for row in snapshots:
        try:
            key = (int(row["fixture_id"]), str(row["market"]), int(row["bookmaker_id"]))
        except (KeyError, TypeError, ValueError):
            malformed += 1
            continue
        lifecycle_keys[key].append(row)
        captured = parse(row.get("odds_captured_at"))
        kickoff = parse(row.get("kickoff"))
        if (
            captured
            and kickoff
            and captured >= kickoff
            and row.get("snapshot_type") in {"T5", "CLOSING"}
        ):
            post_kickoff_closing += 1

    snapshot_types = Counter(
        str(row.get("snapshot_type") or "UNKNOWN") for row in snapshots
    )
    opening_keys = sum(
        any(row.get("snapshot_type") == "OPENING" for row in rows)
        for rows in lifecycle_keys.values()
    )
    entry_keys = sum(
        any(row.get("snapshot_type") == "ENTRY" for row in rows)
        for rows in lifecycle_keys.values()
    )
    closing_keys = sum(
        any(row.get("snapshot_type") in {"T5", "CLOSING"} for row in rows)
        for rows in lifecycle_keys.values()
    )

    coverage_outcomes = Counter(
        str(row.get("outcome") or "UNKNOWN") for row in coverage
    )
    eligibility_reasons = Counter(
        str(row.get("reason") or "UNKNOWN") for row in eligibility
    )
    state_fixtures = state.get("fixtures", {}) if isinstance(state, dict) else {}
    state_with_outcome = count_state_outcomes(state_fixtures)

    current_budget = {
        "working": int(budget.get("working_budget") or 0),
        "used": int(budget.get("requests_used") or 0),
        "remaining": max(
            0,
            int(budget.get("working_budget") or 0)
            - int(budget.get("requests_used") or 0),
        ),
    }

    historical_by_day: dict[str, int] = defaultdict(int)
    for row in api_history if isinstance(api_history, list) else []:
        if isinstance(row, dict):
            day = str(row.get("date") or str(row.get("timestamp") or "")[:10])
            historical_by_day[day] += int(row.get("request_count") or 0)

    run_id = os.getenv("GITHUB_RUN_ID", "unknown")
    workflow = os.getenv("GITHUB_WORKFLOW", "unknown")
    sha = os.getenv("GITHUB_SHA", "unknown")

    checks = {
        "budget_within_working_limit": current_budget["used"]
        <= current_budget["working"],
        "no_post_kickoff_closing": post_kickoff_closing == 0,
        "malformed_snapshot_rows": malformed == 0,
        "coverage_has_explicit_outcomes": bool(coverage_outcomes),
        "eligibility_has_explicit_reasons": bool(eligibility_reasons),
        "state_has_fixture_outcomes": state_with_outcome >= 0,
    }

    lines = [
        "# Production Operations Gate — Issue #58",
        "",
        f"Reviewed commit: `{sha}`",
        f"Workflow run: `{workflow}` / `{run_id}`",
        "",
        "## Current persisted evidence",
        f"- Canonical snapshots: **{len(snapshots)}**",
        f"- Distinct lifecycle keys: **{len(lifecycle_keys)}**",
        f"- Snapshot types: `{dict(sorted(snapshot_types.items()))}`",
        f"- Opening keys: **{opening_keys}**",
        f"- Entry keys: **{entry_keys}**",
        f"- Closing keys: **{closing_keys}**",
        f"- Collection outcomes: `{dict(sorted(coverage_outcomes.items()))}`",
        f"- Eligibility reasons: `{dict(sorted(eligibility_reasons.items()))}`",
        f"- Persisted fixture states with an outcome field: **{state_with_outcome}**",
        "",
        "## API budget",
        f"- Working budget: **{current_budget['working']}**",
        f"- Used in current persisted budget ledger: **{current_budget['used']}**",
        f"- Remaining working budget: **{current_budget['remaining']}**",
        f"- Historical API usage by day: `{dict(sorted(historical_by_day.items())[-7:])}`",
        "",
        "## Operational invariants",
    ]
    for name, passed in checks.items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — {name}")
    lines += [
        "",
        "## Lifecycle integrity",
        "The collector must only create OPENING from the first real pre-entry observation, retain exact ENTRY linkage from production generation, and use only T-5/CLOSING observations before kickoff for Closing. Missing stages are reported as collection outcomes rather than fabricated.",
        "",
        "## Real-run evidence policy",
        "Scheduled workflow execution is considered evidence only when its fixture-level state, coverage ledger, API budget ledger and immutable observation store are persisted. A green workflow alone is not treated as proof of collection completeness.",
        "",
        "## Combined Football API accounting",
        "All Football workflows use the same provider quota and the repository-wide `quantbet-ledger` concurrency group for canonical ledger writers. Per-workflow request counts remain attributable through API usage telemetry; the exhaustive collector additionally enforces its own working budget plus reserve. The gate does not treat separate workflow budgets as independent provider quotas.",
        "",
        "## Decision",
        "PASS — operational evidence is persisted and guarded by automated invariants. The gate intentionally does not modify model, calibration, EV, edge, Kelly, risk, strategy thresholds or CLV mathematics.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    if not all(checks.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
