from datetime import UTC, datetime
from pathlib import Path

from quantbot.market_timing import append_snapshots
from quantbot.watchlist import cadence_seconds


def test_adaptive_cadence_is_more_frequent_near_kickoff() -> None:
    assert cadence_seconds(7 * 3600) == 3600
    assert cadence_seconds(5 * 3600) == 1800
    assert cadence_seconds(90 * 60) == 600
    assert cadence_seconds(45 * 60) == 300
    assert cadence_seconds(20 * 60) == 180
    assert cadence_seconds(5 * 60) == 120


def test_market_timing_snapshots_are_immutable_and_deduplicated(tmp_path: Path) -> None:
    snapshot = {
        "observation_id": "abc123",
        "captured_at": datetime.now(UTC).isoformat(),
        "fixture_id": 123,
        "prediction_id": "p-123",
        "market": "HOME",
        "odd": 2.1,
        "signal_state": "NEAR_MISS",
    }

    first = append_snapshots(tmp_path, [snapshot], api_requests=1)
    second = append_snapshots(tmp_path, [snapshot], api_requests=1)

    assert first == {"snapshots_appended": 1, "useful_observations": 1}
    assert second == {"snapshots_appended": 0, "useful_observations": 0}
    lines = (tmp_path / "data/market_timing_snapshots.jsonl").read_text().splitlines()
    assert len(lines) == 1
    metrics = (tmp_path / "market_timing_metrics.json").read_text()
    assert '"total_snapshots": 1' in metrics
