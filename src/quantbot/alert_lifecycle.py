from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .api import APIError, APIFootballClient
from .config import Settings
from .markets import extract_best_quotes
from .monitor import (
    FINISHED_STATUSES,
    REVIEW_STATUSES,
    VOID_STATUSES,
    market_outcome,
    regulation_score,
)
from .parsing import parse_datetime
from .types import Market

ALERT_FILE = "intraday_alerts.json"


def _load_alerts(root: Path) -> list[dict[str, Any]]:
    path = root / ALERT_FILE
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _save_alerts(root: Path, alerts: list[dict[str, Any]]) -> None:
    path = root / ALERT_FILE
    path.write_text(
        json.dumps(alerts[-1000:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _clv_pct(entry_odd: float, closing_odd: float) -> float | None:
    if entry_odd > 1.0 and closing_odd > 1.0:
        return round((entry_odd / closing_odd) - 1.0, 6)
    return None


def _apply_closing(alert: dict[str, Any], quote: Any, captured_at: datetime) -> None:
    if alert.get("closing_5m_odd") is not None:
        return
    alert["closing_5m_odd"] = round(quote.odd, 4)
    alert["closing_5m_opposite_odd"] = round(quote.opposite_odd, 4)
    alert["closing_5m_market_probability_devig"] = round(quote.devig_probability, 6)
    alert["closing_5m_odds_captured_at"] = captured_at.isoformat()
    clv = _clv_pct(float(alert.get("odd") or 0.0), float(quote.odd))
    if clv is not None:
        alert["clv_odds_pct"] = clv


def capture_alert_closing_quotes(settings: Settings, now: datetime | None = None) -> int:
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    alerts = _load_alerts(settings.root)
    api = APIFootballClient(settings)
    captured = 0
    changed = False

    for alert in alerts:
        if str(alert.get("status", "")).upper() != "PENDING":
            continue
        if alert.get("closing_5m_odd") is not None:
            continue
        try:
            kickoff = parse_datetime(str(alert["kickoff"]))
            fixture_id = int(alert["event_id"])
            bookmaker_id = int(alert["bookmaker_id"])
            market = Market.parse(str(alert["market"]))
        except (KeyError, TypeError, ValueError):
            continue
        seconds = (kickoff - now_utc).total_seconds()
        if not 120.0 <= seconds <= 480.0:
            continue
        try:
            raw = api.odds(fixture_id)
        except APIError as exc:
            print(f"⚠️ Alert T-5 {alert.get('id')}: {exc}")
            continue
        quotes = extract_best_quotes(
            raw,
            bookmaker_priority=(bookmaker_id,),
            allow_any_bookmaker=False,
            captured_at=now_utc,
            only_bookmaker_id=bookmaker_id,
        )
        quote = quotes.get(market)
        if quote is None or not 0.0 <= quote.overround <= settings.max_market_overround:
            continue
        _apply_closing(alert, quote, now_utc)
        captured += 1
        changed = True

    if changed:
        _save_alerts(settings.root, alerts)
    return captured


def _copy_linked_result(alert: dict[str, Any], bet: dict[str, Any]) -> bool:
    if str(bet.get("status", "")).upper() == "PENDING":
        return False
    changed = False
    for key in ("status", "profit", "result", "outcome", "settled_at"):
        if bet.get(key) is not None and alert.get(key) != bet[key]:
            alert[key] = bet[key]
            changed = True
    for key in (
        "closing_5m_odd",
        "closing_5m_opposite_odd",
        "closing_5m_market_probability_devig",
        "closing_5m_odds_captured_at",
    ):
        if bet.get(key) is not None and alert.get(key) != bet[key]:
            alert[key] = bet[key]
            changed = True
    if changed:
        alert["settlement_type"] = "LINKED_BET"
        clv = _clv_pct(
            float(alert.get("odd") or 0.0),
            float(alert.get("closing_5m_odd") or bet.get("closing_odd") or 0.0),
        )
        if clv is not None:
            alert["clv_odds_pct"] = clv
    return changed


def _settle_counterfactual(
    alert: dict[str, Any],
    status: str,
    score: tuple[int, int] | None,
    now: datetime,
) -> bool:
    if status in VOID_STATUSES:
        alert.update(
            {
                "status": "VOID",
                "profit": 0.0,
                "settled_at": now.isoformat(),
                "result": status,
            }
        )
        return True
    if status in REVIEW_STATUSES or status not in FINISHED_STATUSES or score is None:
        return False
    try:
        won = market_outcome(Market.parse(str(alert["market"])), *score)
    except (KeyError, ValueError):
        alert.update(
            {
                "status": "REVIEW",
                "profit": 0.0,
                "settled_at": now.isoformat(),
                "result": f"{score[0]}:{score[1]}",
            }
        )
        return True
    stake = float(alert.get("stake") or 0.0)
    odd = float(alert.get("odd") or 1.0)
    alert.update(
        {
            "status": "WIN" if won else "LOSS",
            "profit": round(stake * (odd - 1.0), 2) if won else -stake,
            "result": f"{score[0]}:{score[1]}",
            "settled_at": now.isoformat(),
            "settlement_type": "COUNTERFACTUAL_ALERT",
        }
    )
    closing = float(alert.get("closing_5m_odd") or 0.0)
    clv = _clv_pct(odd, closing)
    if clv is not None:
        alert["clv_odds_pct"] = clv
    return True


def settle_intraday_alerts(settings: Settings, now: datetime | None = None) -> int:
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    alerts = _load_alerts(settings.root)
    if not alerts:
        return 0
    bets = (
        json.loads(settings.bets_file.read_text(encoding="utf-8"))
        if settings.bets_file.exists()
        else []
    )
    linked = {str(b.get("id")): b for b in bets if isinstance(b, dict)}
    api = APIFootballClient(settings)
    fixture_cache: dict[int, tuple[str, tuple[int, int] | None]] = {}
    changed_count = 0
    changed = False

    for alert in alerts:
        if str(alert.get("status", "")).upper() != "PENDING":
            continue
        linked_id = str(alert.get("linked_bet_id") or "")
        if linked_id and linked_id in linked:
            if _copy_linked_result(alert, linked[linked_id]):
                changed_count += 1
                changed = True
            continue
        try:
            kickoff = parse_datetime(str(alert["kickoff"]))
            fixture_id = int(alert["event_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if now_utc < kickoff + timedelta(minutes=90):
            continue
        if fixture_id not in fixture_cache:
            try:
                response = api.fixture(fixture_id)
            except APIError as exc:
                print(f"⚠️ Alert settlement {alert.get('id')}: {exc}")
                continue
            if not response:
                continue
            payload = response[0]
            status = str(
                ((payload.get("fixture") or {}).get("status") or {}).get("short")
                or ""
            )
            score = regulation_score(payload) if status in FINISHED_STATUSES else None
            fixture_cache[fixture_id] = (status, score)
        status, score = fixture_cache[fixture_id]
        if _settle_counterfactual(alert, status, score, now_utc):
            changed_count += 1
            changed = True

    if changed:
        _save_alerts(settings.root, alerts)
    return changed_count
