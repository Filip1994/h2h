import json
from datetime import UTC, datetime, timedelta

from tools.system_health import check_system_health


def write_json(root, name, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def base_row(status="PENDING", kickoff=None):
    return {
        "id": "bet-1",
        "event_id": 123,
        "match": "A vs B",
        "kickoff": kickoff or "2026-09-09T16:00:00+00:00",
        "status": status,
    }


def test_stale_pending_is_a_system_failure(tmp_path):
    now = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)
    write_json(
        tmp_path,
        "bets.json",
        [base_row(kickoff="2026-09-09T17:00:00+00:00")],
    )
    write_json(tmp_path, "intraday_alerts.json", [])

    report = check_system_health(tmp_path, now=now)

    assert report["status"] == "FAIL"
    assert report["production_active_count"] == 1
    assert any(e["error"] == "STALE_ACTIVE" for e in report["errors"])


def test_malformed_active_record_cannot_hide_from_health(tmp_path):
    now = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)
    row = base_row()
    row["kickoff"] = "not-a-date"
    write_json(tmp_path, "bets.json", [row])
    write_json(tmp_path, "intraday_alerts.json", [])

    report = check_system_health(tmp_path, now=now)

    assert report["status"] == "FAIL"
    assert any(e["error"] == "ACTIVE_MISSING_VALID_KICKOFF" for e in report["errors"])


def test_terminal_without_settlement_timestamp_is_failure(tmp_path):
    now = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)
    write_json(tmp_path, "bets.json", [base_row(status="WIN")])
    write_json(tmp_path, "intraday_alerts.json", [])

    report = check_system_health(tmp_path, now=now)

    assert report["status"] == "FAIL"
    assert any(e["error"] == "TERMINAL_MISSING_SETTLED_AT" for e in report["errors"])


def test_healthy_active_record_is_not_false_positive(tmp_path):
    now = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)
    kickoff = (now - timedelta(minutes=30)).isoformat()
    write_json(tmp_path, "bets.json", [base_row(kickoff=kickoff)])
    write_json(tmp_path, "intraday_alerts.json", [])

    report = check_system_health(tmp_path, now=now)

    assert report["status"] == "OK"
    assert report["active_count"] == 1
