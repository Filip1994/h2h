from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

FUNNEL_SEMANTICS = {
    "discovered": "Raw fixtures returned by the fixture discovery call for the run.",
    "eligible": "Discovered fixtures that pass status, time-window and league eligibility checks.",
    "modelled": "Eligible fixtures for which the model successfully produced probabilities and expected goals.",
    "predictions": "Market-level prediction records produced from successfully modelled fixtures.",
    "odds_available": "Modelled fixtures for which the provider returned at least one valid market quote.",
    "valid_quotes": "Market-level quotes accepted by the quote normalizer and available for strategy evaluation.",
    "candidates": "Market-level candidates that pass all existing odds/EV/edge gates.",
    "ev_pass": "Market-level evaluations that pass the configured EV threshold.",
    "edge_pass": "Market-level candidates that pass the configured probability-edge threshold.",
    "risk_checks": "Candidates presented to the existing staking/risk allocator.",
    "selected": "Candidates selected by the existing allocator before persistence.",
    "persisted_bets": "Production bets successfully appended by the idempotent BetStore.",
    "settled": "Production bets that subsequently reach a terminal settlement state.",
}


def _fixture_failure_counts(diagnostics: tuple[str, ...]) -> dict[str, int]:
    counts = {"api": 0, "dixon_coles": 0, "other": 0}
    for diagnostic in diagnostics:
        if not diagnostic.startswith("fixture_"):
            continue
        if "API " in diagnostic or "API greška" in diagnostic or "API mrežna" in diagnostic:
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
        return {key: max(0, int(value.get(key, 0))) for key in FUNNEL_SEMANTICS}
    return {
        "discovered": int(telemetry.get("fixtures_discovered", 0)),
        "eligible": int(telemetry.get("fixtures_eligible", 0)),
        "modelled": int(telemetry.get("fixtures_modelled", 0)),
        "predictions": int(telemetry.get("predictions_generated", 0)),
        "odds_available": int(telemetry.get("odds_available", 0)),
        "valid_quotes": int(telemetry.get("valid_quotes", 0)),
        "candidates": int(telemetry.get("candidates_qualified", telemetry.get("candidates", 0))),
        "ev_pass": int(telemetry.get("ev_pass", 0)),
        "edge_pass": int(telemetry.get("edge_pass", 0)),
        "risk_checks": int(telemetry.get("risk_checks", telemetry.get("candidates_qualified", 0))),
        "selected": int(telemetry.get("selected", telemetry.get("selections_produced", 0))),
        "persisted_bets": int(telemetry.get("selections_produced", 0)),
        "settled": int(telemetry.get("settled", 0)),
    }


def _classification_reasons(usage: dict[str, Any], telemetry: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if usage.get("rate_limit_events", 0):
        reasons.append("API_RATE_LIMIT")
    if usage.get("api_error_events", 0):
        reasons.append("API_ERROR")
    if usage.get("network_error_events", 0):
        reasons.append("NETWORK_ERROR")
    if usage.get("budget_exhaustion_events", 0):
        reasons.append("API_BUDGET_EXHAUSTED")
    if telemetry.get("global_quota", {}).get("quota_pressure_state") not in (None, "HEALTHY"):
        reasons.append("GLOBAL_QUOTA_PRESSURE")
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
    fixture_failures = telemetry.get("fixture_failures") or _fixture_failure_counts(result.diagnostics)
    telemetry["fixture_failures"] = fixture_failures
    funnel = _funnel(telemetry)
    telemetry["funnel"] = funnel
    degraded_reasons = _classification_reasons(usage, telemetry)

    return {
        "schema_version": 4,
        "timestamp": generated_at.astimezone(UTC).isoformat(),
        "status": "DEGRADED" if degraded_reasons else "HEALTHY",
        "classification_reasons": degraded_reasons,
        "pipeline": telemetry,
        "funnel": funnel,
        "funnel_semantics": FUNNEL_SEMANTICS,
        "funnel_rejections": list(telemetry.get("funnel_rejections", [])),
        "fixture_failures": fixture_failures,
        "api": usage,
        "new_bets": len(result.new_bets),
        "diagnostic_count": len(result.diagnostics),
        "observation_only": True,
        "threshold_action": "NO_AUTOMATIC_BLOCKING",
    }


def build_failure_health(generated_at: datetime, api_usage: dict[str, Any], error: BaseException, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
    pipeline = dict(telemetry or {})
    pipeline.setdefault("fixture_failures", {"api": 0, "dixon_coles": 0, "other": 0})
    funnel = _funnel(pipeline)
    pipeline["funnel"] = funnel
    return {
        "schema_version": 4,
        "timestamp": generated_at.astimezone(UTC).isoformat(),
        "status": "BLOCKED",
        "classification_reasons": [type(error).__name__],
        "pipeline": pipeline,
        "funnel": funnel,
        "funnel_semantics": FUNNEL_SEMANTICS,
        "funnel_rejections": list(pipeline.get("funnel_rejections", [])),
        "fixture_failures": pipeline["fixture_failures"],
        "api": dict(api_usage),
        "new_bets": 0,
        "diagnostic_count": 0,
        "observation_only": True,
        "threshold_action": "NO_AUTOMATIC_BLOCKING",
    }
