from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .league_registry import AFRICA_COUNTRIES, classification_for_fixture

_GENERAL_EXCLUDED_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bu[\s._-]?(?:17|18|19|20|21|22|23)\b",
        r"\bsub[\s._-]?(?:17|18|19|20|21|22|23)\b",
        r"\b(?:youth|junior(?:s)?|reserve(?:s)?|amateur(?:s)?|academy)\b",
        r"\b(?:b[\s._-]?team|second[\s._-]?team)\b",
        r"\b(?:oberliga|district|5th[\s._-]?division|mls[\s._-]?next[\s._-]?pro)\b",
    )
)

_TEAM_SUFFIX_PATTERNS = (
    re.compile(r"(?:^|[\s._()/-])ii\)?$", re.IGNORECASE),
    re.compile(r"(?:^|[\s._()/-])b\)?$", re.IGNORECASE),
)

ELIGIBILITY_REASONS = frozenset(
    {
        "ELIGIBLE",
        "INELIGIBLE_TIER",
        "INELIGIBLE_COUNTRY",
        "UNKNOWN_LEAGUE_TIER",
        "EXPLICIT_EXCLUSION",
    }
)


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason: str
    provider_league_id: int | None
    country: str
    league_name: str
    tier: int | None


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def contains_excluded_keyword(*values: str | None) -> bool:
    combined = " | ".join(normalize_text(value) for value in values)
    return any(pattern.search(combined) for pattern in _GENERAL_EXCLUDED_PATTERNS)


def _emit_eligibility_event(decision: EligibilityDecision) -> None:
    path_value = os.getenv("QUANTBOT_ELIGIBILITY_LEDGER")
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider_league_id": decision.provider_league_id,
        "country": decision.country,
        "league": decision.league_name,
        "tier": decision.tier,
        "eligible": decision.eligible,
        "reason": decision.reason,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def eligibility_decision(
    country: str | None,
    league_id: int | None,
    league_name: str | None,
    home_name: str | None,
    away_name: str | None,
    excluded_countries: tuple[str, ...] = (),
) -> EligibilityDecision:
    normalized_country = normalize_text(country)
    normalized_league = normalize_text(league_name)

    if normalized_country in {normalize_text(item) for item in excluded_countries}:
        decision = EligibilityDecision(
            False,
            "INELIGIBLE_COUNTRY",
            league_id,
            normalized_country,
            normalized_league,
            None,
        )
        _emit_eligibility_event(decision)
        return decision

    if contains_excluded_keyword(league_name, home_name, away_name):
        decision = EligibilityDecision(
            False,
            "EXPLICIT_EXCLUSION",
            league_id,
            normalized_country,
            normalized_league,
            None,
        )
        _emit_eligibility_event(decision)
        return decision

    if normalized_country in AFRICA_COUNTRIES and normalized_country not in {
        "egypt",
        "morocco",
    }:
        decision = EligibilityDecision(
            False,
            "INELIGIBLE_COUNTRY",
            league_id,
            normalized_country,
            normalized_league,
            None,
        )
        _emit_eligibility_event(decision)
        return decision

    classification = classification_for_fixture(league_id, country, league_name)
    if classification is None:
        decision = EligibilityDecision(
            False,
            "UNKNOWN_LEAGUE_TIER",
            league_id,
            normalized_country,
            normalized_league,
            None,
        )
        _emit_eligibility_event(decision)
        return decision

    if normalize_text(classification.country) != normalized_country:
        decision = EligibilityDecision(
            False,
            "UNKNOWN_LEAGUE_TIER",
            league_id,
            normalized_country,
            normalized_league,
            classification.tier,
        )
        _emit_eligibility_event(decision)
        return decision

    if classification.tier not in (1, 2) or not classification.enabled:
        decision = EligibilityDecision(
            False,
            "INELIGIBLE_TIER",
            league_id,
            normalized_country,
            normalized_league,
            classification.tier,
        )
        _emit_eligibility_event(decision)
        return decision

    if normalize_text(classification.league_name) != normalized_league:
        decision = EligibilityDecision(
            False,
            "UNKNOWN_LEAGUE_TIER",
            league_id,
            normalized_country,
            normalized_league,
            classification.tier,
        )
        _emit_eligibility_event(decision)
        return decision

    normalized_teams = (normalize_text(home_name), normalize_text(away_name))
    if any(
        pattern.search(team)
        for team in normalized_teams
        for pattern in _TEAM_SUFFIX_PATTERNS
    ):
        decision = EligibilityDecision(
            False,
            "EXPLICIT_EXCLUSION",
            league_id,
            normalized_country,
            normalized_league,
            classification.tier,
        )
        _emit_eligibility_event(decision)
        return decision

    decision = EligibilityDecision(
        True,
        "ELIGIBLE",
        league_id,
        normalized_country,
        normalized_league,
        classification.tier,
    )
    _emit_eligibility_event(decision)
    return decision


def is_allowed_match(
    country: str | None,
    league_name: str | None,
    home_name: str | None,
    away_name: str | None,
    excluded_countries: tuple[str, ...] = (),
    league_id: int | None = None,
) -> bool:
    return eligibility_decision(
        country,
        league_id,
        league_name,
        home_name,
        away_name,
        excluded_countries,
    ).eligible
