from datetime import UTC, datetime, timedelta

import pytest

from backtest import selection_statistics, validate_odds_snapshot
from quantbot.types import MatchRecord


def test_selection_statistics_are_chronological_and_clustered() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {
            "event_id": index,
            "kickoff": (start + timedelta(days=index)).isoformat(),
            "market": "OVER_2_5",
            "profit_units": 1.0 if index % 3 else -1.0,
        }
        for index in range(40)
    ]
    stats = selection_statistics(list(reversed(rows)))
    assert stats["selected_bets"] == 40
    assert stats["independent_matchdays"] == 40
    assert stats["flat_stake_roi"] == pytest.approx(0.3)
    assert stats["roi_95_ci_day_cluster_bootstrap"] is not None
    assert stats["max_losing_streak"] == 1


def test_selection_statistics_withholds_interval_for_small_sample() -> None:
    stats = selection_statistics(
        [
            {
                "event_id": 1,
                "kickoff": "2026-01-01T12:00:00+00:00",
                "market": "UNDER_2_5",
                "profit_units": -1.0,
            }
        ]
    )
    assert stats["flat_stake_roi"] == -1.0
    assert stats["max_drawdown_flat_stake_units"] == 1.0
    assert stats["roi_95_ci_day_cluster_bootstrap"] is None


def test_backtest_rejects_post_kickoff_odds() -> None:
    kickoff = datetime(2026, 1, 2, 18, 0, tzinfo=UTC)
    record = MatchRecord(
        fixture_id=1,
        date=kickoff,
        league_id=1,
        league_name="League",
        country="Country",
        season=2026,
        home_id=1,
        home_name="Home",
        away_id=2,
        away_name="Away",
        home_goals=2,
        away_goals=1,
    )
    row = {
        "bookmaker_id": "8",
        "odds_captured_at": kickoff.isoformat(),
        "over_2_5_odd": "1.90",
    }
    with pytest.raises(ValueError, match="kvote nisu pre-match"):
        validate_odds_snapshot(row, record, 7)
