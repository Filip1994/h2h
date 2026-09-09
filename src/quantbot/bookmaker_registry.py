from __future__ import annotations

from typing import Any

# The provider archive audited in Issue #50 does not expose bookmaker logos.
# These two sources are deliberately explicit and auditable. Unknown bookmakers
# render without a logo instead of falling back to guessed domains/favicons.
BOOKMAKER_REGISTRY: dict[int, dict[str, Any]] = {
    8: {
        "name": "Bet365",
        "logo_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Bet_365_logo.png",
        "logo_source": "https://commons.wikimedia.org/wiki/File:Bet_365_logo.png",
        "source_verified": True,
    },
    11: {
        "name": "1xBet",
        "logo_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/1xbetlogo.png",
        "logo_source": "https://commons.wikimedia.org/wiki/File:1xbetlogo.png",
        "source_verified": True,
    },
}


def bookmaker_identity(
    bookmaker_id: int | None, bookmaker_name: str | None = None
) -> dict[str, Any]:
    try:
        bid = int(bookmaker_id) if bookmaker_id is not None else None
    except (TypeError, ValueError):
        bid = None
    entry = dict(BOOKMAKER_REGISTRY.get(bid, {}))
    name = str(bookmaker_name or entry.get("name") or "Bookmaker")
    verified = bool(entry.get("source_verified"))
    return {
        "bookmaker_id": bid,
        "bookmaker": name,
        "logo_url": entry.get("logo_url") if verified else None,
        "logo_source": entry.get("logo_source") if verified else None,
        "logo_verified": verified,
    }
