from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from .league_registry import classification_for, REGISTRY

PACKET_SCHEMA_VERSION = 2
STRATEGY_VERSION = "production-decision-v1"
BOOKMAKER_POLICY_VERSION = "all-provider-bookmakers-best-price-v1"


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def settings_hash(settings: Any) -> str:
    fields = getattr(settings, "__dataclass_fields__", {})
    payload = {}
    for name in fields:
        if name in {"api_key", "gmail_app_pass"}:
            continue
        value = getattr(settings, name)
        if hasattr(value, "as_posix"):
            value = value.as_posix()
        elif isinstance(value, tuple):
            value = list(value)
        payload[name] = value
    return _hash(payload)


def registry_snapshot(league_id: int | None) -> dict[str, Any]:
    """Return the exact registry fingerprint and classification used by a decision."""
    registry_payload = {
        str(key): {
            "provider_league_id": value.provider_league_id,
            "country": value.country,
            "league_name": value.league_name,
            "tier": value.tier,
            "enabled": value.enabled,
            "source": value.source,
        }
        for key, value in sorted(REGISTRY.items())
    }
    classification = classification_for(league_id)
    return {
        "version": _hash(registry_payload),
        "league_id": league_id,
        "classification": (
            {
                "provider_league_id": classification.provider_league_id,
                "country": classification.country,
                "league_name": classification.league_name,
                "tier": classification.tier,
                "enabled": classification.enabled,
                "source": classification.source,
            }
            if classification is not None
            else None
        ),
    }


def build_packet(
    candidate: Any,
    stake: float,
    *,
    settings: Any,
    decision_timestamp: datetime,
    calibration_hash: str | None,
) -> dict[str, Any]:
    quote = candidate.quote
    decision_at = decision_timestamp.astimezone(UTC).isoformat()
    code_sha = os.getenv("GITHUB_SHA") or "LOCAL_UNPINNED"
    observation_payload = {
        "fixture_id": candidate.fixture_id,
        "market": candidate.market.value,
        "bookmaker_id": quote.bookmaker_id,
        "bookmaker": quote.bookmaker_name,
        "odd": round(quote.odd, 6),
        "opposite_odd": round(quote.opposite_odd, 6),
        "captured_at": quote.captured_at.astimezone(UTC).isoformat(),
        "snapshot_type": "ENTRY",
    }
    observation_id = _hash(observation_payload)
    registry = registry_snapshot(candidate.league_id)
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": _hash(
            [
                candidate.fixture_id,
                candidate.market.value,
                quote.bookmaker_id,
                quote.captured_at.astimezone(UTC).isoformat(),
                decision_at,
                code_sha,
            ]
        ),
        "fixture": {
            "fixture_id": candidate.fixture_id,
            "league_id": candidate.league_id,
            "league": f"{candidate.country} - {candidate.league_name}",
            "home_id": candidate.home_id,
            "home": candidate.home_name,
            "away_id": candidate.away_id,
            "away": candidate.away_name,
            "kickoff": candidate.kickoff.astimezone(UTC).isoformat(),
        },
        "decision": {
            "market": candidate.market.value,
            "selection": candidate.market.value,
            "bookmaker_id": quote.bookmaker_id,
            "bookmaker": quote.bookmaker_name,
            "pick_odd": round(quote.odd, 6),
            "pick_observed_at": quote.captured_at.astimezone(UTC).isoformat(),
            "pick_observation_id": observation_id,
            "decision_timestamp": decision_at,
        },
        "model": {
            "version": candidate.model_version,
            "code_sha": code_sha,
            "training_cutoff": candidate.model_training_cutoff,
            "training_sample": {
                "fitted_matches": candidate.model_fitted_matches,
                "team_count": candidate.model_team_count,
                "identity": candidate.model_training_identity,
            },
            "raw_probability": round(candidate.model_probability, 8),
            "calibrated_probability": round(candidate.calibrated_probability, 8),
            "decision_probability": round(candidate.decision_probability, 8),
            "calibration_status": candidate.calibration_status,
            "calibration_hash": calibration_hash,
        },
        "market_inputs": {
            "opposite_odd": round(quote.opposite_odd, 6),
            "devig_probability": round(quote.devig_probability, 8),
            "overround": round(quote.overround, 8),
            "expected_value": round(candidate.expected_value, 8),
            "probability_edge": round(candidate.probability_edge, 8),
            "haircut": round(
                candidate.model_probability - candidate.decision_probability, 8
            ),
        },
        "strategy": {
            "version": STRATEGY_VERSION,
            "config_hash": settings_hash(settings),
            "bookmaker_policy_version": BOOKMAKER_POLICY_VERSION,
            "eligibility": "PASSED",
            "registry_version": registry["version"],
            "registry_league_id": registry["league_id"],
            "registry_classification": registry["classification"],
        },
        "risk": {
            "stake": round(float(stake), 2),
            "kelly_fraction": float(settings.kelly_fraction),
            "max_bet_stake_pct": float(settings.max_bet_stake_pct),
            "max_daily_risk_pct": float(settings.max_daily_risk_pct),
            "max_open_risk_pct": float(settings.max_open_risk_pct),
        },
        "provenance": {
            "canonical_observation_id": observation_id,
            "canonical_observation": observation_payload,
            "opening": {
                "status": "UNAVAILABLE_AT_DECISION_TIME",
                "reason": "NO_EARLIER_OBSERVATION",
            },
            "closing": {
                "status": "UNAVAILABLE_AT_DECISION_TIME",
                "reason": "NOT_YET_OBSERVED",
            },
        },
    }
    packet["integrity_hash"] = _hash(packet)
    return packet


def verify_packet(packet: dict[str, Any]) -> bool:
    expected = packet.get("integrity_hash")
    if not expected:
        return False
    body = dict(packet)
    body.pop("integrity_hash", None)
    return _hash(body) == expected
