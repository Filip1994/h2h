from __future__ import annotations

from datetime import datetime
from typing import Any

from .types import Market, OddsQuote


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 1.0 else None


def _bookmaker_id(bookmaker: dict[str, Any]) -> int | None:
    try:
        return int(bookmaker.get("id"))
    except (TypeError, ValueError):
        return None


def _bookmaker_values(bookmaker: dict[str, Any]) -> dict[str, dict[str, float]]:
    parsed: dict[str, dict[str, float]] = {}
    for bet in bookmaker.get("bets") or []:
        name = str(bet.get("name") or "").strip().casefold()
        values: dict[str, float] = {}
        for item in bet.get("values") or []:
            odd = _as_float(item.get("odd"))
            if odd is not None:
                values[str(item.get("value") or "").strip().casefold()] = odd
        parsed[name] = values
    return parsed


def extract_best_quotes(
    raw_odds: list[dict[str, Any]],
    *,
    bookmaker_priority: tuple[int, ...],
    allow_any_bookmaker: bool,
    captured_at: datetime,
    only_bookmaker_id: int | None = None,
) -> dict[Market, OddsQuote]:
    bookmakers: list[dict[str, Any]] = []
    for payload in raw_odds:
        bookmakers.extend(
            item for item in (payload.get("bookmakers") or []) if isinstance(item, dict)
        )

    def collect(pool: list[dict[str, Any]]) -> dict[Market, OddsQuote]:
        collected: dict[Market, OddsQuote] = {}
        for bookmaker in pool:
            bookmaker_id = _bookmaker_id(bookmaker)
            if bookmaker_id is None:
                continue
            bookmaker_name = str(bookmaker.get("name") or f"Bookmaker {bookmaker_id}")
            values = _bookmaker_values(bookmaker)
            totals = values.get("goals over/under", {})
            btts = values.get("both teams score", {})

            pairs = {
                Market.OVER_25: (totals.get("over 2.5"), totals.get("under 2.5")),
                Market.UNDER_25: (totals.get("under 2.5"), totals.get("over 2.5")),
                Market.BTTS_YES: (btts.get("yes"), btts.get("no")),
            }
            for market, (odd, opposite_odd) in pairs.items():
                if odd is None or opposite_odd is None:
                    continue
                quote = OddsQuote(
                    market=market,
                    odd=odd,
                    opposite_odd=opposite_odd,
                    bookmaker_id=bookmaker_id,
                    bookmaker_name=bookmaker_name,
                    captured_at=captured_at,
                )
                current = collected.get(market)
                if current is None or quote.odd > current.odd:
                    collected[market] = quote
        return collected

    if only_bookmaker_id is not None:
        return collect(
            [item for item in bookmakers if _bookmaker_id(item) == only_bookmaker_id]
        )

    preferred = [
        item for item in bookmakers if _bookmaker_id(item) in bookmaker_priority
    ]
    quotes = collect(preferred)
    if allow_any_bookmaker and len(quotes) < len(Market):
        fallback = collect(bookmakers)
        for market, quote in fallback.items():
            quotes.setdefault(market, quote)
    return quotes
