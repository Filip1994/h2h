from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .api import BaseballAPIClient
from .budget import allocate_budget, rank_games


@dataclass(frozen=True, slots=True)
class BaseballGameSnapshot:
    game_id: int
    captured_at: datetime
    payload: dict[str, Any]
    request_budget_assigned: int


class BaseballPipeline:
    """Phase 1 ingestion pipeline.

    It intentionally stops before prediction/betting until the paid API feed is activated
    and the raw-data schema has been validated against live responses.
    """

    def __init__(self, client: BaseballAPIClient) -> None:
        self.client = client

    def daily_games(self, date_iso: str) -> list[dict[str, Any]]:
        return self.client.games_by_date(date_iso)

    def plan_refresh_budget(
        self,
        games: list[tuple[int, datetime]],
        now: datetime,
        *,
        reserve: int = 500,
    ) -> dict[int, int]:
        priorities = rank_games(games, now)
        return allocate_budget(
            self.client.settings.api_request_budget, priorities, reserve=reserve
        )
