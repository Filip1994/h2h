from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantbot.baseball.api import BaseballAPIClient, BaseballAPIError
from quantbot.baseball.config import BaseballSettings


def parse_game_time(game: dict) -> datetime | None:
    value = game.get("date")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def game_key(game: dict) -> int | None:
    value = game.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def priority(game: dict, now: datetime) -> tuple[float, int]:
    start = parse_game_time(game)
    gid = game_key(game) or 0
    if start is None:
        return (10_000.0, gid)
    minutes = (start - now).total_seconds() / 60.0
    # Prefer upcoming games, especially those entering the key timing windows.
    if minutes >= 0:
        if minutes <= 30:
            score = 0.0
        elif minutes <= 60:
            score = 1.0
        elif minutes <= 180:
            score = 2.0
        elif minutes <= 360:
            score = 3.0
        elif minutes <= 720:
            score = 4.0
        else:
            score = 5.0
    else:
        score = 8.0 + min(abs(minutes) / 60.0, 24.0)
    return (score, gid)


def select_games(games: list[dict], now: datetime, limit: int) -> list[dict]:
    unique: dict[int, dict] = {}
    for game in games:
        gid = game_key(game)
        if gid is not None:
            unique[gid] = game

    # First pass: one game per league to avoid starving smaller competitions.
    by_league: dict[str, list[dict]] = {}
    for game in unique.values():
        league = game.get("league") or {}
        league_id = str(league.get("id", "unknown"))
        by_league.setdefault(league_id, []).append(game)

    for items in by_league.values():
        items.sort(key=lambda item: priority(item, now))

    selected: list[dict] = []
    for league_id in sorted(by_league):
        if len(selected) >= limit:
            break
        selected.append(by_league[league_id][0])

    selected_ids = {game_key(game) for game in selected}
    remainder = [game for game in unique.values() if game_key(game) not in selected_ids]
    remainder.sort(key=lambda item: priority(item, now))
    selected.extend(remainder[: max(0, limit - len(selected))])
    return selected


def compact_line(game: dict, odds: list[dict], captured_at: str) -> dict:
    return {
        "captured_at": captured_at,
        "game": game,
        "odds": odds,
    }


def main() -> int:
    settings = BaseballSettings.from_env(ROOT)
    client = BaseballAPIClient(settings)
    now = datetime.now(timezone.utc)

    # Query both UTC dates so late-night/early-morning games are not missed.
    dates = [now.date().isoformat(), (now + timedelta(days=1)).date().isoformat()]
    games: list[dict] = []
    for date_iso in dates:
        games.extend(client.games_by_date(date_iso))

    limit = max(0, client.remaining_budget)
    # Leave a small margin for retries and a future schema probe.
    limit = min(limit, int(os.getenv("BASEBALL_MAX_ODDS_CALLS", "298")))
    selected = select_games(games, now, limit)

    lines: list[str] = []
    captured_at = now.isoformat()
    for game in selected:
        gid = game_key(game)
        if gid is None:
            continue
        try:
            odds = client.odds(gid)
        except BaseballAPIError as exc:
            odds = [{"_collector_error": str(exc)}]
        lines.append(json.dumps(compact_line(game, odds, captured_at), ensure_ascii=False, separators=(",", ":")))

    out_dir = ROOT / "data" / "baseball" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{now.date().isoformat()}.jsonl"
    run_header = {
        "type": "run",
        "captured_at": captured_at,
        "games_discovered": len({game_key(g) for g in games if game_key(g) is not None}),
        "games_sampled": len(selected),
        "api_requests_used": client.request_count,
        "cache_hits": client.cache_hits,
        "budget": settings.api_request_budget,
    }
    with out_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run_header, ensure_ascii=False, separators=(",", ":")) + "\n")
        for line in lines:
            handle.write(line + "\n")

    print(json.dumps({**run_header, "output": str(out_file.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
