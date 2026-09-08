from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


FUNNEL_SEMANTICS = {
    "discovered": "Raw fixtures returned by the fixture discovery call for the run.",
    "eligible": "Discovered fixtures that pass status, time-window, duplicate-block and league eligibility checks.",
    "modelled": "Eligible fixtures for which the model successfully produced probabilities and expected goals; odds availability is not required for this stage.",
    "predictions": "Market-level prediction records produced from successfully modelled fixtures.",
    "candidates": "Fixture-level candidates retained after at least one market passes the existing EV/edge/odds gates.",
    "selections": "Final bets appended by the existing allocation and BetStore selection path.",
}


def _fixture_failure_counts(diagnostics: tuple[str, ...]) -> dict[str, int]:
    counts = {"api": 0, "dixon_coles": 0, "other": 0}
    for diagnostic in diagnostics:
        if not diagnostic.startswith("fixture_"):
            continue
        if (
            "API " in diagnostic
            or "API greška" in diagnostic
            or "API mrežna" in diagnostic
        ):
            counts["api"] += 1
        elif "Dixon" in diagnostic or "dovoljan trening" in diagnostic:
            counts["dixon_coles"] += 1
        else:
            counts["other"] += 1
    return counts


def _telemetry(result: Any) -> dict[str, Any]:
    value = getattr(result, "telemetry", {})
    return dict(value) if isinstance(value, dict) else {}


def _funnel(telemetry: dict[str, Any]) -> dict[str, int]:
    value = telemetry.get("funnel")
    if isinstance(value, dict):
        return {
            key: max(0, int(value.get(key, 0)))
            for key in FUNNEL_SEMANTICS
        }
    return {
        "discovered": int(telemetry.get("fixtures_discovered", 0)),
        "eligible": int(telemetry.get("fixtures_eligible", 0)),
        "modelled": int(telemetry.get("fixtures_modelled", 0)),
        "predictions": int(telemetry.get("predictions_generated", 0)),
        "candidates": int(telemetry.get("candidates", telemetry.get("candidates_qualified", 0))),
        "selections": int(telemetry.get("selections_produced", 0)),
    }


def _classification_reasons(
    usage: dict[str, Any], telemetry: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    if usage.get("rate_limit_events", 0):
        reasons.append("API_RATE_LIMIT")
    if usage.get("api_error_events", 0):
        reasons.append("API_ERROR")
    if usage.get("network_error_events", 0):
        reasons.append("NETWORK_ERROR")
    if usage.get("budget_exhaustion_events", 0):
        reasons.append("API_BUDGET_EXHAUSTED")
    fixture_failures = telemetry.get("fixture_failures", {})
    if fixture_failures.get("api", 0):
        reasons.append("FIXTURE_API_ERROR")
    if fixture_failures.get("dixon_coles", 0):
        reasons.append("DIXON_COLES_FIXTURE_FAILURE")
    if fixture_failures.get("other", 0):
        reasons.append("FIXTURE_PROCESSING_FAILURE")
    if telemetry.get("training_sample_insufficiency", 0):
        reasons.append("TRAINING_SAMPLE_INSUFFICIENT")
    return reasons


def build_success_health(generated_at: datetime, result: Any) -> dict[str, Any]:
    usage = dict(result.api_usage)
    telemetry = _telemetry(result)
    fixture_failures = telemetry.get("fixture_failures") or _fixture_failure_counts(
        result.diagnostics
    )
    telemetry["fixture_failures"] = fixture_failures
    funnel = _funnel(telemetry)
    telemetry["funnel"] = funnel
    degraded_reasons = _classification_reasons(usage, telemetry)

    return {
        "schema_version": 3,
        "timestamp": generated_at.astimezone(UTC).isoformat(),
        "status": "DEGRADED" if degraded_reasons else "HEALTHY",
        "classification_reasons": degraded_reasons,
        "pipeline": telemetry,
        "funnel": funnel,
        "funnel_semantics": FUNNEL_SEMANTICS,
        "fixture_failures": fixture_failures,
        "api": usage,
        "new_bets": len(result.new_bets),
        "diagnostic_count": len(result.diagnostics),
        "observation_only": True,
        "threshold_action": "NO_AUTOMATIC_BLOCKING",
    }


def build_failure_health(
    generated_at: datetime,
    api_usage: dict[str, Any],
    error: BaseException,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pipeline = dict(telemetry or {})
    pipeline.setdefault("fixture_failures", {"api": 0, "dixon_coles": 0, "other": 0})
    funnel = _funnel(pipeline)
    pipeline["funnel"] = funnel
    return {
        "schema_version": 3,
        "timestamp": generated_at.astimezone(UTC).isoformat(),
        "status": "BLOCKED",
        "classification_reasons": [type(error).__name__],
        "pipeline": pipeline,
        "funnel": funnel,
        "funnel_semantics": FUNNEL_SEMANTICS,
        "fixture_failures": pipeline["fixture_failures"],
        "api": dict(api_usage),
        "new_bets": 0,
        "diagnostic_count": 0,
        "observation_only": True,
        "threshold_action": "NO_AUTOMATIC_BLOCKING",
    }
