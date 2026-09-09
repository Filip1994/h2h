from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.settlement_health import check_settlement_health

ROOT = Path(__file__).resolve().parents[1]


def test_stale_pending_is_detected(tmp_path):
    old = datetime(2026, 9, 8, 1, 0, tzinfo=UTC).isoformat()
    (tmp_path / "bets.json").write_text(
        json.dumps(
            [{"id": "bet-1", "event_id": 123, "kickoff": old, "status": "PENDING"}]
        )
    )
    (tmp_path / "intraday_alerts.json").write_text("[]")
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    report = check_settlement_health(tmp_path, now, max_age_minutes=30)
    assert report["status"] == "FAIL"
    assert report["stale_pending_count"] == 1


def test_recent_pending_is_not_stale(tmp_path):
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    recent = (now - timedelta(minutes=100)).isoformat()
    (tmp_path / "bets.json").write_text(
        json.dumps(
            [{"id": "bet-1", "event_id": 123, "kickoff": recent, "status": "PENDING"}]
        )
    )
    (tmp_path / "intraday_alerts.json").write_text("[]")
    report = check_settlement_health(tmp_path, now, max_age_minutes=30)
    assert report["status"] == "OK"
    assert report["stale_pending_count"] == 0


def test_settlement_health_script_is_directly_executable():
    result = subprocess.run(
        [sys.executable, "tools/settlement_health.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
