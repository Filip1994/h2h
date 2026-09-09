from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.generation_health import build_failure_health, build_success_health


def _result(telemetry, new_bets=0):
    return SimpleNamespace(
        telemetry=telemetry,
        api_usage={
            "rate_limit_events": 0,
            "api_error_events": 0,
            "network_error_events": 0,
            "budget_exhaustion_events": 0,
            "global_quota": {"quota_pressure_state": "HEALTHY"},
        },
        diagnostics=(),
        new_bets=tuple({"id": str(index)} for index in range(new_bets)),
    )


def test_complete_funnel_is_preserved_and_selected_is_pre_persistence() -> None:
    telemetry = {
        "fixtures_discovered": 10,
        "fixtures_eligible": 8,
        "fixtures_modelled": 7,
        "predictions_generated": 21,
        "odds_available": 6,
        "valid_quotes": 15,
        "candidates": 5,
        "ev_pass": 9,
        "edge_pass": 7,
        "risk_checks": 5,
        "risk_selected": 4,
        "selected": 3,
        "selections_produced": 2,
        "settled": 0,
        "risk_rejections": 1,
        "strength_rejections": 1,
        "duplicate_rejections": 1,
        "funnel_rejections": [
            {"stage": "risk_staking", "reason": "RISK_OR_CAPACITY"},
            {"stage": "selected", "reason": "STRONG_SIGNAL_THRESHOLD"},
            {"stage": "persisted_bet", "reason": "DUPLICATE_OR_BLOCKED"},
        ],
    }
    health = build_success_health(
        datetime(2026, 9, 9, 20, 0, tzinfo=UTC), _result(telemetry, new_bets=2)
    )

    assert health["status"] == "DEGRADED"
    assert health["funnel"] == {
        "discovered": 10,
        "eligible": 8,
        "modelled": 7,
        "predictions": 21,
        "odds_available": 6,
        "valid_quotes": 15,
        "candidates": 5,
        "ev_pass": 9,
        "edge_pass": 7,
        "risk_checks": 5,
        "selected": 3,
        "persisted_bets": 2,
        "settled": 0,
    }
    assert "RISK_OR_CAPACITY_REJECTIONS" in health["classification_reasons"]
    assert "STRONG_SIGNAL_THRESHOLD_REJECTIONS" in health["classification_reasons"]
    assert "DUPLICATE_OR_BLOCKED_REJECTIONS" in health["classification_reasons"]
    assert len(health["funnel_rejections"]) == 3


def test_failure_health_keeps_partial_funnel_and_persistence_reason() -> None:
    telemetry = {
        "fixtures_discovered": 4,
        "fixtures_eligible": 3,
        "fixtures_modelled": 2,
        "predictions_generated": 6,
        "persistence_failures": 1,
        "funnel_rejections": [
            {"stage": "persisted_bet", "reason": "BET_PERSISTENCE_FAILURE"}
        ],
    }
    error = RuntimeError("ledger write failed")
    error.telemetry = telemetry
    health = build_failure_health(
        datetime(2026, 9, 9, 20, 0, tzinfo=UTC),
        {"global_quota": {"quota_pressure_state": "HEALTHY"}},
        error,
    )

    assert health["status"] == "BLOCKED"
    assert health["funnel"]["discovered"] == 4
    assert health["funnel"]["predictions"] == 6
    assert health["pipeline"]["persistence_failures"] == 1
    assert "PERSISTENCE_FAILURE" in health["classification_reasons"]
    assert health["funnel_rejections"][0]["reason"] == "BET_PERSISTENCE_FAILURE"
