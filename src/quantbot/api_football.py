from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .types import MatchRecord


_FINISHED = frozenset({"FT", "AET", "PEN"})


def _parse_datetime(value: str) -> datetime:
    """Parse API-Football ISO timestamps and normalize them to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def is_finished_fixture(fixture: dict[str, Any]) -> bool:
    return fixture.get("fixture", {}).get("status", {}).get("short") in _FINISHED


def fixture_to_match_record(fixture: dict[str, Any]) -> MatchRecord | None:
    """Convert one API-Football response item into the legacy MatchRecord.

    Returns None for fixtures without a final score or with incomplete team/
    league metadata. The legacy Dixon-Coles fitter must receive completed
    matches only.
    """
    if not is_finished_fixture(fixture):
        return None

    fixture_data = fixture.get("fixture") or {}
    league = fixture.get("league") or {}
    teams = fixture.get("teams") or {}
    goals = fixture.get("goals") or {}
    score = fixture.get("score") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}

    required = (
        fixture_data.get("id"),
        fixture_data.get("date"),
        league.get("id"),
        league.get("name"),
        league.get("country"),
        league.get("season"),
        home.get("id"),
        home.get("name"),
        away.get("id"),
        away.get("name"),
        goals.get("home"),
        goals.get("away"),
    )
    if any(value is None for value in required):
        return None

    halftime = score.get("halftime") or {}
    return MatchRecord(
        fixture_id=int(fixture_data["id"]),
        date=_parse_datetime(fixture_data["date"]),
        league_id=int(league["id"]),
        league_name=str(league["name"]),
        country=str(league["country"]),
        season=int(league["season"]),
        home_id=int(home["id"]),
        home_name=str(home["name"]),
        away_id=int(away["id"]),
        away_name=str(away["name"]),
        home_goals=int(goals["home"]),
        away_goals=int(goals["away"]),
        halftime_home=_int_or_none(halftime.get("home")),
        halftime_away=_int_or_none(halftime.get("away")),
    )


def load_api_football_json(path: str | Path) -> list[dict[str, Any]]:
    """Load the `response` array from an API-Football JSON export."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    response = payload.get("response")
    if not isinstance(response, list):
        raise ValueError("JSON ne sadrži očekivani API-Football niz: response")
    return response


def to_match_records(fixtures: Iterable[dict[str, Any]]) -> list[MatchRecord]:
    """Convert completed fixtures, preserving API order."""
    records: list[MatchRecord] = []
    for fixture in fixtures:
        record = fixture_to_match_record(fixture)
        if record is not None:
            records.append(record)
    return records


def load_match_records(path: str | Path) -> list[MatchRecord]:
    return to_match_records(load_api_football_json(path))


def records_to_dicts(records: Iterable[MatchRecord]) -> list[dict[str, Any]]:
    """Useful for JSON/CSV export and inspection."""
    return [asdict(record) for record in records]


def summarize_fixtures(fixtures: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic ingestion diagnostics without changing the data."""
    fixtures = list(fixtures)
    statuses: dict[str, int] = {}
    leagues: dict[str, int] = {}
    for fixture in fixtures:
        status = str(
            (fixture.get("fixture") or {}).get("status", {}).get("short") or "UNKNOWN"
        )
        statuses[status] = statuses.get(status, 0) + 1
        league = fixture.get("league") or {}
        league_key = f"{league.get('country', 'UNKNOWN')} - {league.get('name', 'UNKNOWN')}"
        leagues[league_key] = leagues.get(league_key, 0) + 1

    return {
        "fixtures_total": len(fixtures),
        "finished_total": sum(statuses.get(status, 0) for status in _FINISHED),
        "statuses": dict(sorted(statuses.items())),
        "leagues_total": len(leagues),
        "leagues": dict(sorted(leagues.items())),
    }
