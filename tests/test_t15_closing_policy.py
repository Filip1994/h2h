from datetime import UTC, datetime, timedelta

from quantbot.odds_lifecycle import clv_from_odds, select_closing


def row(at, odd, snapshot_type="INTERMEDIATE"):
    return {
        "fixture_id": 1,
        "market": "OVER_2_5",
        "bookmaker_id": 10,
        "selection": "OVER_2_5",
        "odd": odd,
        "opposite_odd": 1.8,
        "odds_captured_at": at.isoformat(),
        "snapshot_type": snapshot_type,
        "snapshot_id": f"{at.isoformat()}-{odd}",
    }


def test_select_closing_prefers_nearest_to_t15():
    kickoff = datetime(2026, 9, 11, 18, 0, tzinfo=UTC)
    observations = [
        row(kickoff - timedelta(minutes=20), 2.0),
        row(kickoff - timedelta(minutes=15), 1.9, "CLOSING"),
        row(kickoff - timedelta(minutes=10), 1.8),
        row(kickoff - timedelta(minutes=5), 1.7, "T5"),
    ]
    selected = select_closing(observations, kickoff)
    assert selected is not None
    assert selected["odd"] == 1.9
    assert selected["snapshot_type"] == "CLOSING"


def test_select_closing_rejects_t5_when_t15_window_missing():
    kickoff = datetime(2026, 9, 11, 18, 0, tzinfo=UTC)
    observations = [row(kickoff - timedelta(minutes=5), 1.7, "T5")]
    assert select_closing(observations, kickoff) is None


def test_clv_uses_t15_closing_odd():
    assert clv_from_odds(2.0, 1.9) == 0.052632
