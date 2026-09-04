from __future__ import annotations

import re
import unicodedata

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


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def contains_excluded_keyword(*values: str | None) -> bool:
    combined = " | ".join(normalize_text(value) for value in values)
    return any(pattern.search(combined) for pattern in _GENERAL_EXCLUDED_PATTERNS)


def is_allowed_match(
    country: str | None,
    league_name: str | None,
    home_name: str | None,
    away_name: str | None,
    excluded_countries: tuple[str, ...] = (),
) -> bool:
    normalized_country = normalize_text(country)
    if normalized_country in {normalize_text(item) for item in excluded_countries}:
        return False
    if contains_excluded_keyword(league_name, home_name, away_name):
        return False
    normalized_teams = (normalize_text(home_name), normalize_text(away_name))
    return not any(
        pattern.search(team)
        for team in normalized_teams
        for pattern in _TEAM_SUFFIX_PATTERNS
    )
