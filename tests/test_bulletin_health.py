from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tools.bulletin_health import (
    build_success_marker,
    business_date,
    is_successful_for_today,
    write_success_marker,
)

TZ = "Europe/Belgrade"


def _now(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_success_marker_is_business_day_based() -> None:
    now = _now("2026-09-08T00:10:00+02:00")
    marker = build_success_marker(
        now,
        generation_started_at="2026-09-07T22:05:00+00:00",
        generation_completed_at="2026-09-07T22:08:00+00:00",
    )
    assert marker["business_date"] == "2026-09-08"
    assert marker["timezone"] == TZ
    assert marker["status"] == "SUCCESS"


def test_success_marker_requires_generation_commit_and_send() -> None:
    now = _now("2026-09-08T00:10:00+02:00")
    marker = build_success_marker(
        now,
        generation_started_at="2026-09-07T22:05:00+00:00",
        generation_completed_at="2026-09-07T22:08:00+00:00",
    )
    assert is_successful_for_today(marker, now)
    marker["send_status"] = "FAIL"
    assert not is_successful_for_today(marker, now)


def test_previous_business_day_is_not_healthy_today() -> None:
    now = _now("2026-09-08T00:10:00+02:00")
    marker = {
        "business_date": "2026-09-07",
        "status": "SUCCESS",
        "generation_status": "SUCCESS",
        "commit_status": "SUCCESS",
        "send_status": "SUCCESS",
        "completed_at": "2026-09-07T22:08:00+00:00",
    }
    assert business_date(now) == "2026-09-08"
    assert not is_successful_for_today(marker, now)


def test_marker_round_trip(tmp_path: Path) -> None:
    now = _now("2026-09-08T00:10:00+02:00")
    marker = build_success_marker(
        now,
        generation_started_at="2026-09-07T22:05:00+00:00",
        generation_completed_at="2026-09-07T22:08:00+00:00",
    )
    path = tmp_path / "bulletin_health.json"
    write_success_marker(marker, path)
    assert path.exists()
    assert is_successful_for_today(json.loads(path.read_text()), now)


def test_repeated_health_checks_are_noop_when_success_exists() -> None:
    now = _now("2026-09-08T00:10:00+02:00")
    marker = build_success_marker(
        now,
        generation_started_at="2026-09-07T22:05:00+00:00",
        generation_completed_at="2026-09-07T22:08:00+00:00",
    )
    assert is_successful_for_today(marker, now)
    assert is_successful_for_today(marker, now)
