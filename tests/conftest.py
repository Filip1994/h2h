from __future__ import annotations

import pytest

from quantbot.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    managed = [
        "API_FOOTBALL_KEY",
        "TIMEZONE",
        "PAPER_MODE",
        "MIN_TRAINING_MATCHES",
        "MIN_TEAM_MATCHES",
        "MIN_CALIBRATION_SAMPLES",
        "PROBABILITY_HAIRCUT",
        "MIN_EDGE_PP",
        "MIN_EV",
        "MAX_DAILY_PICKS",
        "MAX_BET_STAKE_PCT",
        "MAX_DAILY_RISK_PCT",
        "MAX_OPEN_RISK_PCT",
    ]
    for name in managed:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("PAPER_MODE", "true")
    monkeypatch.setenv("MIN_TRAINING_MATCHES", "20")
    monkeypatch.setenv("MIN_TEAM_MATCHES", "2")
    monkeypatch.setenv("MIN_CALIBRATION_SAMPLES", "10")
    monkeypatch.setenv("PROBABILITY_HAIRCUT", "0")
    monkeypatch.setenv("MIN_EDGE_PP", "0")
    monkeypatch.setenv("MIN_EV", "0")
    return Settings.from_env(tmp_path)
