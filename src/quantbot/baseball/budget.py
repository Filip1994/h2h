from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GamePriority:
    game_id: int
    minutes_to_start: float
    weight: float


def priority_weight(minutes_to_start: float) -> float:
    """Higher refresh priority as first pitch approaches; no bet timing is changed here."""
    if minutes_to_start <= 15:
        return 8.0
    if minutes_to_start <= 60:
        return 5.0
    if minutes_to_start <= 180:
        return 3.0
    if minutes_to_start <= 360:
        return 2.0
    return 1.0


def rank_games(games: list[tuple[int, datetime]], now: datetime) -> list[GamePriority]:
    ranked: list[GamePriority] = []
    for game_id, start_time in games:
        minutes = (start_time - now).total_seconds() / 60.0
        if minutes < -180:
            continue
        ranked.append(GamePriority(game_id, minutes, priority_weight(minutes)))
    return sorted(ranked, key=lambda item: (-item.weight, item.minutes_to_start, item.game_id))


def allocate_budget(total_budget: int, priorities: list[GamePriority], *, reserve: int = 0) -> dict[int, int]:
    """Allocate a daily request budget by informational priority, not by game count."""
    if total_budget < 0 or reserve < 0 or reserve > total_budget:
        raise ValueError("Invalid budget/reserve")
    if not priorities:
        return {}

    spendable = total_budget - reserve
    total_weight = sum(item.weight for item in priorities)
    allocation = {
        item.game_id: int(spendable * item.weight / total_weight) for item in priorities
    }

    # Preserve at least one request for each selected game while budget allows.
    for item in priorities:
        if allocation[item.game_id] == 0 and spendable > 0:
            allocation[item.game_id] = 1
            spendable -= 1

    # Give remaining requests to the highest-priority games.
    used = sum(allocation.values())
    remaining = max(0, total_budget - reserve - used)
    ordered = sorted(priorities, key=lambda item: (-item.weight, item.minutes_to_start, item.game_id))
    index = 0
    while remaining:
        allocation[ordered[index % len(ordered)].game_id] += 1
        remaining -= 1
        index += 1
    return allocation
