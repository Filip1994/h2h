from types import SimpleNamespace

from quantbot.generation_health import build_success_health


def test_global_quota_pressure_is_classified_from_api_usage(settings):
    result = SimpleNamespace(
        api_usage={
            "global_quota": {"quota_pressure_state": "RESERVE_PRESSURE"},
        },
        telemetry={},
        diagnostics=(),
        new_bets=(),
    )
    health = build_success_health(__import__("datetime").datetime.now(__import__("datetime").UTC), result)
    assert health["status"] == "DEGRADED"
    assert "GLOBAL_QUOTA_PRESSURE" in health["classification_reasons"]
