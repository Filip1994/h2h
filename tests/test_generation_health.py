from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.generation_health import build_failure_health, build_success_health


def _result(*diagnostics: str, telemetry=None, **usage):
    return SimpleNamespace(
        diagnostics=diagnostics,
        api_usage=usage,
        new_bets=(),
        telemetry=telemetry or {},
    )


def test_429_is_classified_as_degraded_without_blocking() -> None:
    result = _result(
        rate_limit_events=1,
        retry_events=1,
        api_error_events=0,
        network_error_events=0,
    )
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "DEGRADED"
    assert "API_RATE_LIMIT" in health["classification_reasons"]
    assert health["api"]["retry_events"] == 1
    assert health["threshold_action"] == "NO_AUTOMATIC_BLOCKING"


def test_fixture_dixon_coles_failure_is_observed_not_blocked() -> None:
    result = _result(
        "fixture_123: Domaći tim nema dovoljan trening uzorak",
        telemetry={
            "fixture_failures": {"api": 0, "dixon_coles": 1, "other": 0},
            "training_sample_insufficiency": 1,
        },
    )
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "DEGRADED"
    assert health["fixture_failures"]["dixon_coles"] == 1
    assert health["pipeline"]["training_sample_insufficiency"] == 1
    assert health["status"] != "BLOCKED"


def test_clean_generation_is_healthy_with_pipeline_counts() -> None:
    telemetry = {
        "fixtures_discovered": 10,
        "fixtures_parse_failures": 0,
        "fixtures_eligible": 4,
        "fixtures_modelled": 4,
        "predictions_generated": 12,
        "candidates_evaluated": 12,
        "candidates_qualified": 2,
        "candidates": 2,
        "selections_produced": 1,
        "training_sample_insufficiency": 0,
        "fit_failures": 0,
        "fixture_failures": {"api": 0, "dixon_coles": 0, "other": 0},
    }
    result = _result(
        telemetry=telemetry,
        rate_limit_events=0,
        retry_events=0,
        budget_exhaustion_events=0,
        api_error_events=0,
        network_error_events=0,
    )
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "HEALTHY"
    assert health["classification_reasons"] == []
    assert health["funnel"] == {
        "discovered": 10,
        "eligible": 4,
        "modelled": 4,
        "predictions": 12,
        "candidates": 2,
        "selections": 1,
    }
    assert health["funnel_semantics"]["candidates"].startswith(
        "Fixture-level candidates"
    )
    assert health["pipeline"]["selections_produced"] == 1


def test_missing_canonical_candidate_counter_is_not_reconstructed() -> None:
    result = _result(
        telemetry={
            "fixtures_discovered": 3,
            "fixtures_eligible": 2,
            "fixtures_modelled": 2,
            "predictions_generated": 6,
            "candidates_qualified": 5,
            "selections_produced": 1,
        },
    )
    health = build_success_health(datetime.now(UTC), result)
    assert health["funnel"]["candidates"] == 0


def test_budget_exhaustion_is_degraded_and_not_a_rpm_threshold() -> None:
    result = _result(
        telemetry={
            "fixture_failures": {"api": 0, "dixon_coles": 0, "other": 0},
        },
        budget_exhaustion_events=1,
        retry_events=0,
        rate_limit_events=0,
        api_error_events=0,
        network_error_events=0,
    )
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "DEGRADED"
    assert "API_BUDGET_EXHAUSTED" in health["classification_reasons"]
    assert "API_RATE_LIMIT" not in health["classification_reasons"]


def test_mixed_degraded_run_exposes_coverage_and_failure_counts() -> None:
    telemetry = {
        "fixtures_discovered": 20,
        "fixtures_parse_failures": 2,
        "fixtures_eligible": 8,
        "fixtures_modelled": 6,
        "predictions_generated": 18,
        "candidates_evaluated": 18,
        "candidates_qualified": 3,
        "candidates": 3,
        "selections_produced": 2,
        "training_sample_insufficiency": 2,
        "fit_failures": 1,
        "fixture_failures": {"api": 1, "dixon_coles": 3, "other": 2},
    }
    result = _result(
        telemetry=telemetry,
        rate_limit_events=1,
        retry_events=2,
        budget_exhaustion_events=0,
        api_error_events=1,
        network_error_events=0,
    )
    health = build_success_health(datetime.now(UTC), result)
    assert health["status"] == "DEGRADED"
    assert {
        "API_RATE_LIMIT",
        "API_ERROR",
        "FIXTURE_API_ERROR",
        "DIXON_COLES_FIXTURE_FAILURE",
        "FIXTURE_PROCESSING_FAILURE",
        "TRAINING_SAMPLE_INSUFFICIENT",
    } <= set(health["classification_reasons"])
    assert health["pipeline"]["fixtures_eligible"] == 8
    assert health["pipeline"]["fit_failures"] == 1
    assert health["funnel"]["candidates"] == 3


def test_fatal_generation_failure_is_classified_blocked_but_observation_only() -> None:
    health = build_failure_health(
        datetime.now(UTC),
        {"rate_limit_events": 2, "retry_events": 2},
        RuntimeError("generation failed"),
        telemetry={"fixtures_discovered": 5},
    )
    assert health["status"] == "BLOCKED"
    assert health["classification_reasons"] == ["RuntimeError"]
    assert health["pipeline"]["fixtures_discovered"] == 5
    assert health["funnel"]["discovered"] == 5
    assert health["observation_only"] is True
    assert health["threshold_action"] == "NO_AUTOMATIC_BLOCKING"
