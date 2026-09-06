from pathlib import Path

import pytest

from quantbot.baseball.api import BaseballAPIBudgetExceeded, BaseballAPIClient
from quantbot.baseball.config import BaseballSettings


def make_settings(tmp_path: Path, budget: int = 2) -> BaseballSettings:
    return BaseballSettings(
        api_key="test-key",
        api_base_url="https://example.invalid",
        api_request_budget=budget,
        api_max_attempts=1,
        api_retry_base_seconds=0.0,
        cache_dir=tmp_path,
        timezone_name="Europe/Belgrade",
        paper_mode=True,
    )


def test_client_starts_with_full_budget(tmp_path: Path) -> None:
    client = BaseballAPIClient(make_settings(tmp_path, 7500))
    assert client.request_count == 0
    assert client.remaining_budget == 7500
    assert client.cache_hits == 0


def test_budget_is_enforced_before_network_call(tmp_path: Path) -> None:
    client = BaseballAPIClient(make_settings(tmp_path, 1))
    client.request_count = 1
    with pytest.raises(BaseballAPIBudgetExceeded):
        client.get("games", {"date": "2026-09-06"})
