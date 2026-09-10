import json
from datetime import UTC, datetime

import pytest

from tools.odds_collection_runtime_audit import audit


def _write_fixture(root, *, queried=1, requests=1):
    run_at = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
    metrics = {
        "timestamp": run_at.isoformat(),
        "eligible_fixtures": 1,
        "queried_fixtures": queried,
        "observations_captured": 2,
        "api_requests_used_this_run": requests,
        "daily_budget_remaining": 100,
        "provider_availability_by_ttk": {"72-48h": 1},
        "actual_scan_timestamps": [run_at.isoformat()] if queried else [],
        "budget_exhausted": 0,
    }
    state = {"fixtures": {"123": {"fixture_id": 123, "kickoff": "2026-09-10T12:00:00+00:00", "last_seen_at": run_at.isoformat()}}}
    coverage = {"captured_at": run_at.isoformat(), "fixture_id": 123, "outcome": "QUERIED"}
    (root / "odds_collection_metrics.json").write_text(json.dumps(metrics))
    (root / "odds_collection_state.json").write_text(json.dumps(state))
    data = root / "data"
    data.mkdir()
    (data / "odds_collection_coverage.jsonl").write_text(json.dumps(coverage) + "\n")


def test_runtime_audit_passes_for_real_scan_evidence(tmp_path):
    _write_fixture(tmp_path)
    result = audit(tmp_path)
    assert result["status"] == "PASS"
    assert result["evidence"]["provider_scan_proven"] is True


def test_runtime_audit_fails_when_eligible_universe_has_no_provider_request(tmp_path):
    _write_fixture(tmp_path, queried=0, requests=0)
    with pytest.raises(SystemExit, match="ELIGIBLE_UNIVERSE_WITHOUT_PROVIDER_REQUEST"):
        audit(tmp_path)


def test_runtime_audit_fails_for_fixture_outside_72h(tmp_path):
    _write_fixture(tmp_path)
    state = json.loads((tmp_path / "odds_collection_state.json").read_text())
    state["fixtures"]["123"]["kickoff"] = "2026-09-14T12:00:00+00:00"
    (tmp_path / "odds_collection_state.json").write_text(json.dumps(state))
    with pytest.raises(SystemExit, match="FIXTURE_OUTSIDE_72H_WINDOW"):
        audit(tmp_path)
