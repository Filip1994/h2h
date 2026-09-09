from __future__ import annotations

from datetime import datetime
from typing import Any

from .types import Market, OddsQuote

# Production bookmaker scope: only Serbian-available operators selected for the
# paper-trading system. This is intentionally a code-level hard whitelist so
# Production, Strong Signals, and Near Misses cannot silently drift to another
# provider. API odds are still fetched once per fixture and filtered locally.
ALLOWED_BOOKMAKER_IDS: frozenset[int] = frozenset({8, 11, 34})


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


def _bookmakers(raw_odds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bookmakers: list[dict[str, Any]] = []
    for payload in raw_odds:
        bookmakers.extend(
            item
            for item in (payload.get("bookmakers") or [])
            if isinstance(item, dict) and _bookmaker_id(item) in ALLOWED_BOOKMAKER_IDS
        )
    return bookmakers


def _quotes_for_bookmaker(
    bookmaker: dict[str, Any], captured_at: datetime
) -> list[OddsQuote]:
    bookmaker_id = _bookmaker_id(bookmaker)
    if bookmaker_id is None or bookmaker_id not in ALLOWED_BOOKMAKER_IDS:
        return []
    bookmaker_name = str(bookmaker.get("name") or f"Bookmaker {bookmaker_id}")
    values = _bookmaker_values(bookmaker)
    totals = values.get("goals over/under", {})
    btts = values.get("both teams score", {})
    pairs = {
        Market.OVER_25: (totals.get("over 2.5"), totals.get("under 2.5")),
        Market.UNDER_25: (totals.get("under 2.5"), totals.get("over 2.5")),
        Market.BTTS_YES: (btts.get("yes"), btts.get("no")),
    }
    quotes: list[OddsQuote] = []
    for market, (odd, opposite_odd) in pairs.items():
        if odd is None or opposite_odd is None:
            continue
        quotes.append(
            OddsQuote(
                market=market,
                odd=odd,
                opposite_odd=opposite_odd,
                bookmaker_id=bookmaker_id,
                bookmaker_name=bookmaker_name,
                captured_at=captured_at,
            )
        )
    return quotes


def extract_all_valid_quotes(
    raw_odds: list[dict[str, Any]], *, captured_at: datetime
) -> list[OddsQuote]:
    """Extract every valid supported quote from the hard-whitelisted bookmakers."""
    quotes: list[OddsQuote] = []
    seen: set[tuple[int, Market, float, float]] = set()
    for bookmaker in _bookmakers(raw_odds):
        for quote in _quotes_for_bookmaker(bookmaker, captured_at):
            identity = (quote.bookmaker_id, quote.market, quote.odd, quote.opposite_odd)
            if identity in seen:
                continue
            seen.add(identity)
            quotes.append(quote)
    return quotes


def extract_best_quotes(
    raw_odds: list[dict[str, Any]],
    *,
    bookmaker_priority: tuple[int, ...],
    allow_any_bookmaker: bool,
    captured_at: datetime,
    only_bookmaker_id: int | None = None,
) -> dict[Market, OddsQuote]:
    """Select the best quote from the Serbian hard whitelist.

    ``bookmaker_priority`` and ``allow_any_bookmaker`` remain accepted for
    backwards-compatible configuration, but neither can expand bookmaker scope.
    Before Pick, the best valid quote is selected only among IDs 8, 11, and 34.
    Once a Pick exists, ``only_bookmaker_id`` locks reads to the exact Pick
    bookmaker and therefore cannot substitute another provider.
    """
    bookmakers = _bookmakers(raw_odds)

    if only_bookmaker_id is not None:
        pool = [item for item in bookmakers if _bookmaker_id(item) == only_bookmaker_id]
    else:
        pool = bookmakers

    collected: dict[Market, OddsQuote] = {}
    for bookmaker in pool:
        for quote in _quotes_for_bookmaker(bookmaker, captured_at):
            current = collected.get(quote.market)
            if current is None or quote.odd > current.odd:
                collected[quote.market] = quote
    return collected
