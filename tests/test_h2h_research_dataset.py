from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from quantbot.h2h import build_h2h_stats_detailed
from quantbot.h2h_telemetry import H2HOutcomeStore, H2HSnapshotStore, build_snapshot, h2h_snapshot_id
from quantbot.types import H2HStats, Market, MatchRecord


def raw_fixture(fixture_id: int, when: datetime, home_goals: int = 1, away_goals: int = 0) -> dict:
    return {
        "fixture": {"id": fixture_id, "date": when.isoformat(), "status": {"short": "FT"}},
        "league": {"id": 10, "name": "Test League", "country": "Testland", "season": when.year},
        "teams": {"home": {"id": 1, "name": "Home"}, "away": {"id": 2, "name": "Away"}},
        "goals": {"home": home_goals, "away": away_goals},
        "score": {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": home_goals, "away": away_goals}},
    }


def test_snapshot_id_is_fixture_and_cutoff_point_in_time() -> None:
    cutoff = datetime(2026, 9, 8, 0, 45, tzinfo=UTC)
    assert h2h_snapshot_id(123, cutoff) == h2h_snapshot_id(123, cutoff)
    assert h2h_snapshot_id(123, cutoff) != h2h_snapshot_id(123, cutoff + timedelta(hours=1))
    assert h2h_snapshot_id(123, cutoff) != h2h_snapshot_id(124, cutoff)


def test_h2h_excludes_future_match_and_returns_explicit_available_status(settings) -> None:
    cutoff = datetime(2026, 9, 8, 0, 45, tzinfo=UTC)
    raw = [
        raw_fixture(index, cutoff - timedelta(days=index * 30), 2, 1)
        for index in range(1, 7)
    ]
    raw.append(raw_fixture(9999, cutoff + timedelta(days=1), 0, 0))
    stats, status = build_h2h_stats_detailed(raw, now=cutoff, settings=settings)
    assert status == "AVAILABLE"
    assert stats is not None
    assert len(stats.matches) == 6
    assert all(record.date < cutoff for record in stats.matches)


def test_statuses_are_explicit(settings) -> None:
    cutoff = datetime(2026, 9, 8, 0, 45, tzinfo=UTC)
    stats, status = build_h2h_stats_detailed([], now=cutoff, settings=settings)
    assert stats is None
    assert status == "INSUFFICIENT_HISTORY"

    old = [raw_fixture(i, cutoff - timedelta(days=900 + i * 10)) for i in range(1, 7)]
    stats, status = build_h2h_stats_detailed(old, now=cutoff, settings=settings)
    assert stats is None
    assert status == "NO_RECENT_HISTORY"


def test_snapshot_store_is_append_only_and_idempotent(tmp_path) -> None:
    cutoff = datetime(2026, 9, 8, 0, 45, tzinfo=UTC)
    stats = H2HStats(
        matches=(MatchRecord(1, cutoff - timedelta(days=30), 10, "Test", "Testland", 2026, 1, "Home", 2, "Away", 2, 0),),
        weighted_rates={Market.OVER_25: 1.0, Market.UNDER_25: 0.0, Market.BTTS_YES: 0.0},
        effective_n=1.0,
        has_recent_match=True,
    )
    snapshot = build_snapshot(
        fixture_id=123,
        decision_timestamp=cutoff,
        home_id=1,
        away_id=2,
        home_name="Home",
        away_name="Away",
        league_id=10,
        league="Testland - Test",
        h2h_enabled=True,
        status="AVAILABLE",
        stats=stats,
    )
    store = H2HSnapshotStore(tmp_path)
    assert store.append(snapshot) == snapshot["h2h_snapshot_id"]
    assert store.append(snapshot) is None
    records = (tmp_path / "data/h2h_snapshots.jsonl").read_text().splitlines()
    assert len(records) == 1
    assert json.loads(records[0])["h2h_matches"][0]["home_goals"] == 2


def test_final_result_mapping_is_1x2_and_idempotent(tmp_path) -> None:
    store = H2HOutcomeStore(tmp_path)
    captured = datetime(2026, 9, 9, tzinfo=UTC)
    assert store.append(snapshot_id="a", fixture_id=1, home_goals=2, away_goals=1, captured_at=captured)
    assert not store.append(snapshot_id="a", fixture_id=1, home_goals=2, away_goals=1, captured_at=captured)
    assert store.append(snapshot_id="b", fixture_id=2, home_goals=1, away_goals=1, captured_at=captured)
    assert store.append(snapshot_id="c", fixture_id=3, home_goals=0, away_goals=2, captured_at=captured)
    rows = [json.loads(line) for line in (tmp_path / "data/h2h_outcomes.jsonl").read_text().splitlines()]
    assert [row["final_result_1x2"] for row in rows] == ["1", "X", "2"]
    assert rows[0]["final_total_goals"] == 3


def test_h2h_telemetry_snapshot_contains_no_moneyline_market() -> None:
    assert set(Market) == {Market.OVER_25, Market.UNDER_25, Market.BTTS_YES}
