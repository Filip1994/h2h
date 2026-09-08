from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.generation_health import build_failure_health, build_success_health


def _result(*diagnostics: str, **usage):
    return SimpleNamespace(
        diagnostics=diagnostics,
        api_usage=usage,
        new_bets=(),
    )


def test_429_is_classified_as_degraded_without_blocking() -> None:
    result = _result(rate_limit_events=1, api_error_events=0, network_error_events=0)
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "DEGRADED"
    assert "API_RATE_LIMIT" in health["classification_reasons"]
    assert health["threshold_action"] == "NO_AUTOMATIC_BLOCKING"


def test_fixture_dixon_coles_failure_is_observed_not_blocked() -> None:
    result = _result("fixture_123: Domaći tim nema dovoljan trening uzorak")
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "DEGRADED"
    assert health["fixture_failures"]["dixon_coles"] == 1
    assert health["status"] != "BLOCKED"


def test_clean_generation_is_healthy() -> None:
    result = _result(rate_limit_events=0, api_error_events=0, network_error_events=0)
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "HEALTHY"
    assert health["classification_reasons"] == []


def test_fatal_generation_failure_is_classified_blocked_but_observation_only() -> None:
    health = build_failure_health(
        datetime.now(UTC),
        {"rate_limit_events": 2},
        RuntimeError("generation failed"),
    )
    assert health["status"] == "BLOCKED"
    assert health["classification_reasons"] == ["RuntimeError"]
    assert health["observation_only"] is True
    assert health["threshold_action"] == "NO_AUTOMATIC_BLOCKING"
