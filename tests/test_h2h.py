from datetime import UTC, datetime

from quantbot.h2h import build_h2h_stats_from_records, format_recent_history
from quantbot.types import Market, MatchRecord


def record(fixture_id: int, date: str, home_goals: int, away_goals: int) -> MatchRecord:
    return MatchRecord(
        fixture_id=fixture_id,
        date=datetime.fromisoformat(date).replace(tzinfo=UTC),
        league_id=1,
        league_name="League",
        country="Country",
        season=2026,
        home_id=1,
        home_name="Home",
        away_id=2,
        away_name="Away",
        home_goals=home_goals,
        away_goals=away_goals,
        halftime_home=1,
        halftime_away=0,
    )


def test_h2h_uses_rolling_window_and_explicit_order(settings) -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    records = [
        record(3, "2025-01-01", 2, 1),
        record(1, "2022-08-01", 4, 0),  # outside exact four-year window
        record(6, "2026-01-01", 1, 1),
        record(2, "2023-01-01", 2, 1),
        record(5, "2025-08-01", 3, 0),
        record(4, "2025-04-01", 0, 1),
    ]
    stats = build_h2h_stats_from_records(records, now=now, settings=settings)
    assert stats is not None
    assert len(stats.matches) == 5
    assert [item.fixture_id for item in stats.matches] == [2, 3, 4, 5, 6]
    assert 0.45 < stats.weighted_rates[Market.OVER_25] < 0.50
    history = format_recent_history(stats)
    assert history[0].startswith("[01.01.2026.]")
    assert history[-1].startswith("[01.01.2023.]")


def test_h2h_requires_recent_match(settings) -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    records = [record(index, f"2023-0{index}-01", 2, 1) for index in range(1, 6)]
    assert build_h2h_stats_from_records(records, now=now, settings=settings) is None
