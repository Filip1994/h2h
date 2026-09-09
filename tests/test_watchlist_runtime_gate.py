from datetime import UTC, datetime, timedelta  # noqa: I001

from tools.watchlist_runtime_gate import evaluate


NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def prediction(hours: float, fixture_id: int = 1) -> dict:
    return {
        "event_id": fixture_id,
        "kickoff": (NOW + timedelta(hours=hours)).isoformat(),
    }


def test_eligible_fixture_with_zero_scan_is_error():
    result = evaluate(
        {"fixtures_scanned": 0, "api_requests": 0},
        [prediction(2)],
        now=NOW,
        lookahead_hours=6,
    )
    assert result["status"] == "ERROR"
    assert "ELIGIBLE_FIXTURES_WITH_ZERO_SCANS" in result["errors"]
    assert "ELIGIBLE_FIXTURES_WITH_ZERO_API_REQUESTS" in result["errors"]


def test_truthful_zero_without_eligible_fixtures_is_not_error():
    result = evaluate(
        {"fixtures_scanned": 0, "api_requests": 0},
        [prediction(12)],
        now=NOW,
        lookahead_hours=6,
    )
    assert result["status"] == "NO_ELIGIBLE_FIXTURES"
    assert result["errors"] == []


def test_scanned_without_api_requests_is_error():
    result = evaluate(
        {"fixtures_scanned": 1, "api_requests": 0},
        [prediction(2)],
        now=NOW,
        lookahead_hours=6,
    )
    assert result["status"] == "ERROR"
    assert "SCANS_REPORTED_WITH_ZERO_API_REQUESTS" in result["errors"]


def test_healthy_eligible_run_passes():
    result = evaluate(
        {"fixtures_scanned": 2, "api_requests": 2},
        [prediction(2, 1), prediction(3, 2)],
        now=NOW,
        lookahead_hours=6,
    )
    assert result["status"] == "OK"
    assert result["eligible_fixture_count"] == 2
