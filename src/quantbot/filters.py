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

# API-Football fixture metadata does not expose a stable competition-tier
# field. Production therefore uses this explicit, deterministic classification.
# Anything not listed is UNKNOWN and is blocked by default. No name heuristic
# is used to infer a tier.
_CANONICAL_LEAGUE_TIERS: dict[tuple[str, str], int] = {
    # England
    ("england", "premier league"): 1,
    ("england", "championship"): 2,
    ("england", "national league"): 3,
    ("england", "league one"): 3,
    ("england", "league two"): 4,
    # Spain
    ("spain", "la liga"): 1,
    ("spain", "laliga"): 1,
    ("spain", "segunda division"): 2,
    ("spain", "primera federacion"): 3,
    ("spain", "primera division rfef - group 1"): 3,
    ("spain", "primera division rfef - group 2"): 3,
    # Italy
    ("italy", "serie a"): 1,
    ("italy", "serie b"): 2,
    ("italy", "serie c - girone a"): 3,
    ("italy", "serie c - girone b"): 3,
    ("italy", "serie c - girone c"): 3,
    # Germany
    ("germany", "bundesliga"): 1,
    ("germany", "2. bundesliga"): 2,
    ("germany", "3. liga"): 3,
    # France
    ("france", "ligue 1"): 1,
    ("france", "ligue 2"): 2,
    ("france", "national"): 3,
    # Netherlands
    ("netherlands", "eredivisie"): 1,
    ("netherlands", "eerste divisie"): 2,
    ("netherlands", "keuken kampioen divisie"): 2,
    # Portugal
    ("portugal", "primeira liga"): 1,
    ("portugal", "liga portugal 2"): 2,
    ("portugal", "segunda liga"): 2,
    # Belgium / Scotland
    ("belgium", "jupiler pro league"): 1,
    ("belgium", "challenger pro league"): 2,
    ("scotland", "premiership"): 1,
    ("scotland", "championship"): 2,
    # Austria / Switzerland
    ("austria", "bundesliga"): 1,
    ("austria", "2. liga"): 2,
    ("switzerland", "super league"): 1,
    ("switzerland", "challenge league"): 2,
    # Denmark / Norway / Sweden / Finland / Iceland
    ("denmark", "superliga"): 1,
    ("denmark", "1. division"): 2,
    ("norway", "eliteserien"): 1,
    ("norway", "1. divisjon"): 2,
    ("sweden", "allsvenskan"): 1,
    ("sweden", "superettan"): 2,
    ("finland", "veikkausliiga"): 1,
    ("finland", "ykkosliiga"): 2,
    ("finland", "ykkonen"): 2,
    ("iceland", "urvalsdeild"): 1,
    ("iceland", "1. deild"): 2,
    # Balkans
    ("serbia", "super liga"): 1,
    ("serbia", "prva liga"): 2,
    ("croatia", "1. hnl"): 1,
    ("croatia", "hnl"): 1,
    ("croatia", "1. nl"): 2,
    ("slovenia", "1. snl"): 1,
    ("slovenia", "2. snl"): 2,
    ("bosnia", "premier league"): 1,
    ("bosnia and herzegovina", "premier league"): 1,
    ("bosnia and herzegovina", "first league"): 2,
    ("montenegro", "1. cfl"): 1,
    ("montenegro", "2. cfl"): 2,
    # Czechia / Slovakia / Poland
    ("czech republic", "czech liga"): 1,
    ("czech republic", "fotbalova narodni liga"): 2,
    ("slovakia", "super liga"): 1,
    ("slovakia", "2. liga"): 2,
    ("poland", "ekstraklasa"): 1,
    ("poland", "i liga"): 2,
    # Greece / Turkey
    ("greece", "super league 1"): 1,
    ("greece", "super league 2"): 2,
    ("turkey", "super lig"): 1,
    ("turkey", "1. lig"): 2,
    # Romania / Bulgaria / Hungary
    ("romania", "liga i"): 1,
    ("romania", "liga ii"): 2,
    ("bulgaria", "first league"): 1,
    ("bulgaria", "second league"): 2,
    ("hungary", "nb i"): 1,
    ("hungary", "nb ii"): 2,
    # Albania / North Macedonia
    ("albania", "superliga"): 1,
    ("albania", "1st division"): 2,
    ("north macedonia", "first league"): 1,
    ("north macedonia", "second league"): 2,
}


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def canonical_league_tier(country: str | None, league_name: str | None) -> int | None:
    return _CANONICAL_LEAGUE_TIERS.get(
        (normalize_text(country), normalize_text(league_name))
    )


def contains_excluded_keyword(*values: str | None) -> bool:
    combined = " | ".join(normalize_text(value) for value in values)
    return any(pattern.search(combined) for pattern in _GENERAL_EXCLUDED_PATTERNS)


def is_allowed_match(
    country: str | None,
    league_name: str | None,
    home_name: str | None,
    away_name: str | None,
    excluded_countries: tuple[str, ...] = (),
    league_tier: object = None,
) -> bool:
    normalized_country = normalize_text(country)
    if normalized_country in {normalize_text(item) for item in excluded_countries}:
        return False

    if league_tier is None:
        tier = canonical_league_tier(country, league_name)
    else:
        try:
            tier = int(league_tier)
        except (TypeError, ValueError):
            tier = None
    if tier not in {1, 2}:
        return False

    if contains_excluded_keyword(league_name, home_name, away_name):
        return False
    normalized_teams = (normalize_text(home_name), normalize_text(away_name))
    return not any(
        pattern.search(team)
        for team in normalized_teams
        for pattern in _TEAM_SUFFIX_PATTERNS
    )
