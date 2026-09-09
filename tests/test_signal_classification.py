from __future__ import annotations

from quantbot.config import Settings
from quantbot.signal_classification import (
    NEAR_MISS,
    OBSERVED,
    STRONG_SIGNAL,
    classify_signal,
)


def settings() -> Settings:
    return Settings.from_env()


def test_strong_requires_all_existing_thresholds() -> None:
    s = settings()
    result = classify_signal(
        expected_value=s.strong_signal_min_ev,
        probability_edge=s.strong_signal_min_edge,
        stake=s.strong_signal_min_stake,
        settings=s,
    )
    assert result.signal_class == STRONG_SIGNAL


def test_strong_boundary_fails_when_stake_is_below_threshold() -> None:
    s = settings()
    result = classify_signal(
        expected_value=s.strong_signal_min_ev,
        probability_edge=s.strong_signal_min_edge,
        stake=s.strong_signal_min_stake - 0.01,
        settings=s,
    )
    assert result.signal_class == NEAR_MISS


def test_near_miss_reason_and_exact_boundary() -> None:
    s = settings()
    result = classify_signal(
        expected_value=s.min_ev - 0.03,
        probability_edge=s.min_edge - 0.05,
        stake=100.0,
        settings=s,
    )
    assert result.signal_class == NEAR_MISS
    assert result.near_miss_reason == "EV_NEAR_THRESHOLD"


def test_observed_is_below_both_near_thresholds() -> None:
    s = settings()
    result = classify_signal(
        expected_value=s.min_ev - 0.031,
        probability_edge=s.min_edge - 0.021,
        stake=100.0,
        settings=s,
    )
    assert result.signal_class == OBSERVED


def test_qualified_is_separate_from_observation_class() -> None:
    s = settings()
    result = classify_signal(
        expected_value=s.min_ev,
        probability_edge=s.min_edge,
        stake=100.0,
        settings=s,
    )
    assert result.qualified_candidate is True
    assert result.signal_class == NEAR_MISS
