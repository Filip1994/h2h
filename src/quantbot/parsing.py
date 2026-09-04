from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .types import MatchRecord


def parse_datetime(value: str | None) -> datetime:
    if not value:
        raise ValueError("Nedostaje datum utakmice")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _required_int(value: Any, field: str) -> int:
    if value is None:
        raise ValueError(f"Nedostaje {field}")
    return int(value)


def match_record_from_api(
    item: dict[str, Any], *, require_ft: bool = True
) -> MatchRecord:
    fixture = item.get("fixture") or {}
    status = fixture.get("status") or {}
    if require_ft and status.get("short") != "FT":
        raise ValueError("Utakmica nije završena u regularnom vremenu")

    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    goals = item.get("goals") or {}
    halftime = (item.get("score") or {}).get("halftime") or {}

    return MatchRecord(
        fixture_id=_required_int(fixture.get("id"), "fixture.id"),
        date=parse_datetime(fixture.get("date")),
        league_id=_required_int(league.get("id"), "league.id"),
        league_name=str(league.get("name") or "Unknown league"),
        country=str(league.get("country") or "Unknown country"),
        season=_required_int(league.get("season"), "league.season"),
        home_id=_required_int(home.get("id"), "home.id"),
        home_name=str(home.get("name") or "Home"),
        away_id=_required_int(away.get("id"), "away.id"),
        away_name=str(away.get("name") or "Away"),
        home_goals=_required_int(goals.get("home"), "goals.home"),
        away_goals=_required_int(goals.get("away"), "goals.away"),
        halftime_home=int(halftime["home"])
        if halftime.get("home") is not None
        else None,
        halftime_away=int(halftime["away"])
        if halftime.get("away") is not None
        else None,
    )


def current_fixture_fields(item: dict[str, Any]) -> dict[str, Any]:
    fixture = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    return {
        "fixture_id": _required_int(fixture.get("id"), "fixture.id"),
        "kickoff": parse_datetime(fixture.get("date")),
        "status": str((fixture.get("status") or {}).get("short") or ""),
        "league_id": _required_int(league.get("id"), "league.id"),
        "league_name": str(league.get("name") or "Unknown league"),
        "country": str(league.get("country") or "Unknown country"),
        "season": _required_int(league.get("season"), "league.season"),
        "home_id": _required_int(home.get("id"), "home.id"),
        "home_name": str(home.get("name") or "Home"),
        "away_id": _required_int(away.get("id"), "away.id"),
        "away_name": str(away.get("name") or "Away"),
    }
