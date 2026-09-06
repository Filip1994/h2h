from datetime import datetime, timedelta, timezone

from quantbot.baseball.budget import allocate_budget, priority_weight, rank_games


def test_priority_increases_near_first_pitch() -> None:
    assert priority_weight(10) > priority_weight(45) > priority_weight(120) > priority_weight(300)


def test_allocator_uses_full_spendable_budget() -> None:
    now = datetime.now(timezone.utc)
    ranked = rank_games(
        [
            (1, now + timedelta(minutes=10)),
            (2, now + timedelta(hours=2)),
            (3, now + timedelta(hours=6)),
        ],
        now,
    )
    allocation = allocate_budget(7500, ranked, reserve=300)
    assert sum(allocation.values()) == 7200
    assert allocation[1] > allocation[2] > allocation[3]


def test_past_games_are_not_prioritized() -> None:
    now = datetime.now(timezone.utc)
    ranked = rank_games([(1, now - timedelta(hours=4))], now)
    assert ranked == []
