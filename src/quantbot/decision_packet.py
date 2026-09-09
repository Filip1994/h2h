from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import MarketCandidate

PACKET_SCHEMA_VERSION = 1
STRATEGY_VERSION = "production-decision-v1"
BOOKMAKER_POLICY_VERSION = "all-provider-bookmakers-best-price-v1"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def config_hash(settings: Any) -> str:
    if is_dataclass(settings):
        payload = asdict(settings)
    else:
        payload = {
            key: value
            for key, value in vars(settings).items()
            if not key.startswith("_")
        }
    for key in ("api_key", "gmail_app_pass"):
        payload.pop(key, None)
    return _stable_hash(payload)


def build_packet(
    candidate: MarketCandidate,
    *,
    stake: float,
    decision_timestamp: datetime,
    settings: Any,
    model_version: str,
    model_fitted_matches: int | None,
    model_team_count: int | None,
    calibration_hash: str | None,
    calibration_status: str,
    observation_id: str | None = None,
) -> dict[str, Any]:
    quote = candidate.quote
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": _stable_hash(
            {
                "fixture_id": candidate.fixture_id,
                "market": candidate.market.value,
                "bookmaker_id": quote.bookmaker_id,
                "decision_timestamp": decision_timestamp.isoformat(),
            }
        ),
        "fixture": {
            "fixture_id": candidate.fixture_id,
            "league_id": candidate.league_id,
            "league": candidate.league_name,
            "country": candidate.country,
            "home_id": candidate.home_id,
            "home": candidate.home_name,
            "away_id": candidate.away_id,
            "away": candidate.away_name,
            "kickoff": candidate.kickoff.isoformat(),
        },
        "market": candidate.market.value,
        "selection": candidate.market.value,
        "bookmaker": {
            "id": quote.bookmaker_id,
            "name": quote.bookmaker_name,
            "policy_version": BOOKMAKER_POLICY_VERSION,
        },
        "pick_observation": {
            "observation_id": observation_id,
            "captured_at": quote.captured_at.isoformat(),
            "odd": quote.odd,
            "opposite_odd": quote.opposite_odd,
            "source": "api-football/odds",
            "unavailable_reason": "not_yet_persisted" if observation_id is None else None,
        },
        "model": {
            "version": model_version,
            "code_sha": os.getenv("GITHUB_SHA"),
            "training_cutoff": decision_timestamp.isoformat(),
            "training_sample": {
                "fitted_matches": model_fitted_matches,
                "team_count": model_team_count,
                "available": model_fitted_matches is not None,
                "unavailable_reason": None if model_fitted_matches is not None else "MODEL_METADATA_UNAVAILABLE",
            },
            "probability": candidate.model_probability,
            "lambda_home": candidate.lambda_home,
            "lambda_away": candidate.lambda_away,
            "rho": candidate.rho,
        },
        "calibration": {
            "status": calibration_status,
            "hash": calibration_hash,
            "calibrated_probability": candidate.calibrated_probability,
            "unavailable_reason": None if calibration_hash else "CALIBRATION_FILE_UNAVAILABLE",
        },
        "market_inputs": {
            "devig_probability": quote.devig_probability,
            "overround": quote.overround,
            "expected_value": candidate.expected_value,
            "probability_edge": candidate.probability_edge,
            "probability_haircut": settings.probability_haircut,
            "decision_probability": candidate.decision_probability,
        },
        "eligibility": {
            "version": "eligibility-v1",
            "status": "ELIGIBLE",
        },
        "strategy": {
            "version": STRATEGY_VERSION,
            "config_hash": config_hash(settings),
        },
        "risk": {
            "kelly_fraction": settings.kelly_fraction,
            "max_bet_stake_pct": settings.max_bet_stake_pct,
            "max_daily_risk_pct": settings.max_daily_risk_pct,
            "max_open_risk_pct": settings.max_open_risk_pct,
            "stake": stake,
        },
        "decision_timestamp": decision_timestamp.isoformat(),
        "immutable": True,
    }
    packet["integrity_hash"] = _stable_hash(packet)
    return packet


def append_unique(path: Path, packet: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if existing.get("packet_id") == packet.get("packet_id"):
                    if existing.get("integrity_hash") != packet.get("integrity_hash"):
                        raise RuntimeError("Decision packet ID collision with different evidence")
                    return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return True
