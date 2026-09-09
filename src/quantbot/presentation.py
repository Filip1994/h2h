from __future__ import annotations

from typing import Any


MARKET_DISPLAY = {
    "OVER_2_5": "Over 2.5",
    "UNDER_2_5": "Under 2.5",
    "BTTS_YES": "BTTS — Yes",
    "BTTS_NO": "BTTS — No",
    "HOME_WIN": "Home Win",
    "AWAY_WIN": "Away Win",
    "DRAW": "Draw",
}

STATUS_DISPLAY = {
    "PENDING": "PENDING",
    "WIN": "WON",
    "LOSS": "LOST",
    "SKIPPED": "SKIPPED",
    "VOID": "VOID",
    "REVIEW": "REVIEW",
}


def market_display(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in MARKET_DISPLAY:
        return MARKET_DISPLAY[raw]
    legacy = {
        "Više 2.5": "Over 2.5",
        "Manje 2.5": "Under 2.5",
        "Less than 2.5": "Under 2.5",
        "Over 2.5": "Over 2.5",
        "Under 2.5": "Under 2.5",
        "GG": "BTTS — Yes",
        "NG": "BTTS — No",
        "BTTS — Yes": "BTTS — Yes",
        "BTTS — No": "BTTS — No",
        "Ukupno Golova - Više 2.5": "Over 2.5",
        "Ukupno Golova - Manje 2.5": "Under 2.5",
        "Oba Tima Daju Gol (GG)": "BTTS — Yes",
    }
    return legacy.get(raw, raw or "—")


def status_display(value: Any) -> str:
    raw = str(value or "PENDING").upper()
    return STATUS_DISPLAY.get(raw, raw)


def clv_percent(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


def clv_label(value: Any) -> str:
    percent = clv_percent(value)
    if percent is None:
        return "—"
    sign = "+" if percent >= 0 else "−"
    return f"{sign}{abs(percent):.2f}%"


def clv_interpretation(value: Any) -> str:
    percent = clv_percent(value)
    if percent is None:
        return "Unavailable"
    return "Beat close" if percent >= 0 else "Lost to close"


def odds_lifecycle(bet: dict[str, Any]) -> dict[str, Any]:
    """Return explicit Opening → Pick → Closing values without inference."""
    return {
        "opening": bet.get("opening_odd"),
        "pick": bet.get("odd"),
        "closing": bet.get("closing_odd") or bet.get("closing_5m_odd"),
        "opening_at": bet.get("opening_odds_captured_at"),
        "pick_at": bet.get("odds_captured_at"),
        "closing_at": bet.get("closing_odds_captured_at")
        or bet.get("closing_5m_odds_captured_at"),
    }


def skip_reason(bet: dict[str, Any]) -> str | None:
    for key in ("skip_reason", "skipped_reason", "reason"):
        value = bet.get(key)
        if value:
            return str(value)
    return None
