from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .api import BaseballAPIBudgetExceeded, BaseballAPIClient, BaseballAPIError

LOCAL_BOOKMAKER_TOKENS = (
    "bet365",
    "1xbet",
    "superbet",
    "mozzart",
    "maxbet",
    "soccerbet",
    "meridian",
    "admiralbet",
    "balkanbet",
)
TARGET_MARKET_TOKENS = (
    "moneyline",
    "winner",
    "run line",
    "spread",
    "total",
    "over/under",
    "strikeout",
    "hits",
    "total bases",
    "runs",
    "rbi",
    "home run",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return " ".join(_text(value).casefold().replace("_", " ").split())


def _game_time(game: dict[str, Any]) -> datetime | None:
    raw = game.get("date")
    if isinstance(raw, dict):
        raw = raw.get("date")
    raw = raw or ((game.get("game") or {}).get("date"))
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(_text(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _game_id(game: dict[str, Any]) -> int | None:
    raw = game.get("id") or (game.get("game") or {}).get("id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _league_name(game: dict[str, Any]) -> str:
    league = game.get("league") or (game.get("game") or {}).get("league") or {}
    if isinstance(league, dict):
        return _text(league.get("name") or league.get("id"))
    return _text(league)


def _team_names(game: dict[str, Any]) -> tuple[str, str]:
    teams = game.get("teams") or {}
    home = teams.get("home") if isinstance(teams, dict) else {}
    away = teams.get("away") if isinstance(teams, dict) else {}
    return _text((home or {}).get("name")), _text((away or {}).get("name"))


def _bookmaker_records(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in payload:
        bookmakers = item.get("bookmakers") or item.get("bookmaker") or []
        if isinstance(bookmakers, dict):
            bookmakers = [bookmakers]
        if not isinstance(bookmakers, list):
            continue
        for bookmaker in bookmakers:
            if not isinstance(bookmaker, dict):
                continue
            name = _text(bookmaker.get("name") or bookmaker.get("bookmaker_name"))
            bets = bookmaker.get("bets") or bookmaker.get("markets") or []
            if isinstance(bets, dict):
                bets = [bets]
            market_rows: list[dict[str, Any]] = []
            if isinstance(bets, list):
                for market in bets:
                    if not isinstance(market, dict):
                        continue
                    market_name = _text(
                        market.get("name") or market.get("label") or market.get("type")
                    )
                    values = market.get("values") or market.get("outcomes") or []
                    if isinstance(values, dict):
                        values = [values]
                    compact_values: list[dict[str, Any]] = []
                    if isinstance(values, list):
                        for value in values:
                            if not isinstance(value, dict):
                                continue
                            row = {
                                "value": value.get("value")
                                or value.get("label")
                                or value.get("name"),
                                "odd": value.get("odd")
                                or value.get("price")
                                or value.get("odds"),
                                "handicap": value.get("handicap") or value.get("point"),
                            }
                            if any(v is not None for v in row.values()):
                                compact_values.append(row)
                    market_rows.append({"name": market_name, "values": compact_values})
            records.append({"name": name, "markets": market_rows})
    return records


def compact_odds(payload: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep a compact, auditable odds footprint while preserving target markets/bookmakers."""
    records = _bookmaker_records(payload)
    bookmakers: list[dict[str, Any]] = []
    market_names: set[str] = set()
    for record in records:
        bookmaker_name = record["name"]
        selected = _norm(bookmaker_name)
        keep_bookmaker = any(token in selected for token in LOCAL_BOOKMAKER_TOKENS)
        markets: list[dict[str, Any]] = []
        for market in record["markets"]:
            market_name = market["name"]
            market_norm = _norm(market_name)
            market_names.add(market_name)
            if keep_bookmaker or any(
                token in market_norm for token in TARGET_MARKET_TOKENS
            ):
                markets.append(market)
        if keep_bookmaker or markets:
            bookmakers.append({"name": bookmaker_name, "markets": markets})
    return {
        "bookmakers": bookmakers,
        "bookmaker_names": sorted({r["name"] for r in records if r["name"]}),
        "market_names": sorted(market_names),
        "coverage_probe": True,
    }


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )


def collect_once(
    root: Path, *, now: datetime | None = None, max_odds_requests: int = 199
) -> dict[str, int]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    from .config import BaseballSettings

    settings = BaseballSettings.from_env(root)
    client = BaseballAPIClient(settings)
    games = client.games_by_date(now.date().isoformat())
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for game in games:
        kickoff = _game_time(game)
        game_id = _game_id(game)
        if kickoff is None or game_id is None:
            continue
        minutes = (kickoff - now).total_seconds() / 60.0
        if -180 <= minutes <= 36 * 60:
            candidates.append((kickoff, game))

    # Guarantee league diversity first, then spend the remaining request budget on games
    # nearest to first pitch. This favors information density without starving smaller
    # leagues that carry odds.
    candidates.sort(
        key=lambda item: (item[0], _league_name(item[1]), _game_id(item[1]) or 0)
    )
    selected: list[dict[str, Any]] = []
    seen_leagues: set[str] = set()
    for _, game in candidates:
        league = _league_name(game) or "UNKNOWN"
        if league not in seen_leagues:
            selected.append(game)
            seen_leagues.add(league)
        if len(selected) >= max_odds_requests:
            break
    if len(selected) < max_odds_requests:
        for _, game in sorted(
            candidates, key=lambda item: abs((item[0] - now).total_seconds())
        ):
            if game in selected:
                continue
            selected.append(game)
            if len(selected) >= max_odds_requests:
                break

    day_path = (
        root / "data" / "baseball" / "snapshots" / f"{now.date().isoformat()}.jsonl"
    )
    coverage_path = root / "data" / "baseball" / "market_coverage.json"
    rows: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    if coverage_path.exists():
        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            coverage = {}

    odds_calls = 0
    games_seen = len(games)
    for game in selected:
        game_id = _game_id(game)
        if game_id is None:
            continue
        try:
            odds = client.odds(game_id)
        except BaseballAPIBudgetExceeded:
            break
        except BaseballAPIError as exc:
            rows.append(
                {
                    "captured_at": now.isoformat(),
                    "game": game,
                    "game_id": game_id,
                    "odds_error": str(exc),
                }
            )
            continue
        odds_calls += 1
        compact = compact_odds(odds)
        league = _league_name(game) or "UNKNOWN"
        existing = coverage.setdefault(league, {"snapshots": 0, "bookmakers": []})
        if not isinstance(existing, dict):
            existing = {"snapshots": 0, "bookmakers": []}
            coverage[league] = existing
        names = set(existing.get("bookmakers") or [])
        names.update(compact["bookmaker_names"])
        existing["bookmakers"] = sorted(names)
        existing["snapshots"] = int(existing.get("snapshots") or 0) + 1
        home, away = _team_names(game)
        kickoff = _game_time(game)
        rows.append(
            {
                "captured_at": now.isoformat(),
                "game_id": game_id,
                "kickoff": kickoff.isoformat() if kickoff else None,
                "league": league,
                "home": home,
                "away": away,
                "game": game,
                "odds": compact,
            }
        )

    _append_jsonl(day_path, rows)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "games_seen": games_seen,
        "games_selected": len(selected),
        "odds_calls": odds_calls,
        "api_requests": client.request_count,
        "rows_written": len(rows),
    }
