from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from tools.settlement_health import check_settlement_health


def _write_inputs(tmp_path, bets):
    (tmp_path / "bets.json").write_text(json.dumps(bets), encoding="utf-8")
    (tmp_path / "intraday_alerts.json").write_text("[]", encoding="utf-8")


def test_active_stale_pending_fails(tmp_path):
    old = datetime(2026, 9, 8, 1, 0, tzinfo=UTC).isoformat()
    _write_inputs(
        tmp_path,
        [{"id": "bet-1", "event_id": 123, "kickoff": old, "status": "PENDING"}],
    )
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    report = check_settlement_health(tmp_path, now, max_age_minutes=30)
    assert report["status"] == "FAIL"
    assert report["stale_pending_count"] == 1
    assert report["active_unresolved_count"] == 1
    assert report["stale_unresolved_count"] == 0
    assert report["active_unresolved"][0]["resolution_status"] == "ACTIVE_UNRESOLVED"


def test_explicit_stale_unresolved_does_not_fail(tmp_path):
    old = datetime(2026, 9, 8, 1, 0, tzinfo=UTC).isoformat()
    _write_inputs(
        tmp_path,
        [
            {
                "id": "alert-1",
                "event_id": 1600773,
                "kickoff": old,
                "status": "PENDING",
                "resolution_status": "STALE_UNRESOLVED",
                "last_settlement_attempt_at": "2026-09-08T04:00:00+00:00",
                "settlement_failure_reason": "FIXTURE_EVIDENCE_UNAVAILABLE",
                "resolution_classified_at": "2026-09-08T04:01:00+00:00",
            }
        ],
    )
    now = datetime(2026, 9, 8, 5, 0, tzinfo=UTC)
    report = check_settlement_health(tmp_path, now, max_age_minutes=30)
    assert report["status"] == "OK_WITH_WARNING"
    assert report["active_unresolved_count"] == 0
    assert report["stale_unresolved_count"] == 1
    stale = report["stale_unresolved"][0]
    assert stale["event_id"] == 1600773
    assert stale["original_status"] == "PENDING"
    assert stale["resolution_status"] == "STALE_UNRESOLVED"
    assert stale["settlement_failure_reason"] == "FIXTURE_EVIDENCE_UNAVAILABLE"


def test_recent_pending_is_not_stale(tmp_path):
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    recent = (now - timedelta(minutes=100)).isoformat()
    _write_inputs(
        tmp_path,
        [{"id": "bet-1", "event_id": 123, "kickoff": recent, "status": "PENDING"}],
    )
    report = check_settlement_health(tmp_path, now, max_age_minutes=30)
    assert report["status"] == "OK"
    assert report["stale_pending_count"] == 0


def test_stale_history_does_not_mask_active_unresolved(tmp_path):
    old = datetime(2026, 9, 8, 1, 0, tzinfo=UTC).isoformat()
    _write_inputs(
        tmp_path,
        [
            {
                "id": "stale-1",
                "event_id": 1,
                "kickoff": old,
                "status": "PENDING",
                "resolution_status": "STALE_UNRESOLVED",
            },
            {
                "id": "active-1",
                "event_id": 2,
                "kickoff": old,
                "status": "PENDING",
            },
        ],
    )
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    report = check_settlement_health(tmp_path, now, max_age_minutes=30)
    assert report["status"] == "FAIL"
    assert report["active_unresolved_count"] == 1
    assert report["stale_unresolved_count"] == 1
    assert report["active_unresolved"][0]["id"] == "active-1"
