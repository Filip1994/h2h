from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .filters import is_allowed_match
from .parsing import match_record_from_api
from .types import H2HStats, Market, MatchRecord


def subtract_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _market_won(record: MatchRecord, market: Market) -> bool:
    total = record.home_goals + record.away_goals
    if market == Market.OVER_25:
        return total >= 3
    if market == Market.UNDER_25:
        return total <= 2
    if market == Market.BTTS_YES:
        return record.home_goals >= 1 and record.away_goals >= 1
    raise ValueError(f"Nepoznat market: {market}")


def build_h2h_stats(
    raw_matches: list[dict[str, Any]],
    *,
    now: datetime,
    settings: Settings,
) -> H2HStats | None:
    cutoff = subtract_years(now, settings.h2h_years)
    matches: list[MatchRecord] = []

    for raw in raw_matches:
        try:
            record = match_record_from_api(raw, require_ft=True)
        except (TypeError, ValueError):
            continue
        if not cutoff <= record.date < now:
            continue
        if not is_allowed_match(
            record.country,
            record.league_name,
            record.home_name,
            record.away_name,
            settings.excluded_countries,
        ):
            continue
        matches.append(record)

    return build_h2h_stats_from_records(matches, now=now, settings=settings)


def build_h2h_stats_from_records(
    records: list[MatchRecord],
    *,
    now: datetime,
    settings: Settings,
) -> H2HStats | None:
    cutoff = subtract_years(now, settings.h2h_years)
    recent_cutoff = now - timedelta(days=settings.max_recent_h2h_days)
    matches = sorted(
        (record for record in records if cutoff <= record.date < now),
        key=lambda item: item.date,
    )
    if len(matches) < settings.min_h2h_matches:
        return None

    has_recent = any(record.date >= recent_cutoff for record in matches)
    if not has_recent:
        return None

    weights = [
        math.exp(
            -settings.dc_xi * max(0.0, (now - record.date).total_seconds() / 86_400.0)
        )
        for record in matches
    ]
    total_weight = sum(weights)
    if total_weight <= 0.0:
        return None
    effective_n = (total_weight * total_weight) / sum(
        weight * weight for weight in weights
    )

    rates = {
        market: sum(
            weight
            for record, weight in zip(matches, weights, strict=True)
            if _market_won(record, market)
        )
        / total_weight
        for market in Market
    }
    return H2HStats(
        matches=tuple(matches),
        weighted_rates=rates,
        effective_n=effective_n,
        has_recent_match=has_recent,
    )


def format_recent_history(stats: H2HStats, limit: int = 5) -> tuple[str, ...]:
    history: list[str] = []
    for record in reversed(stats.matches[-limit:]):
        halftime = ""
        if record.halftime_home is not None and record.halftime_away is not None:
            halftime = f" (HT {record.halftime_home}:{record.halftime_away})"
        history.append(
            f"[{record.date:%d.%m.%Y.}] {record.home_name} {record.home_goals}:{record.away_goals} {record.away_name}{halftime}"
        )
    return tuple(history)
