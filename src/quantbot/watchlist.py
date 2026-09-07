from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alerts import (
    build_strong_signal_email,
    is_strong_signal,
    send_strong_signal_email,
)
from .api import APIBudgetExceeded, APIError, APIFootballClient
from .config import Settings
from .markets import extract_best_quotes
from .risk import kelly_stake, portfolio_analytics
from .storage import BetStore, atomic_write_json
from .types import Market


STATE_FILE = "intraday_watchlist_state.json"
ALERT_FILE = "intraday_alerts.json"


def _load_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _load_state(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _seconds_to_kickoff(kickoff: datetime, now: datetime) -> float:
    return (kickoff.astimezone(UTC) - now.astimezone(UTC)).total_seconds()


def cadence_seconds(seconds_to_kickoff: float) -> int:
    if seconds_to_kickoff > 3 * 3600:
        return 3600
    if seconds_to_kickoff > 2 * 3600:
        return 1800
    if seconds_to_kickoff > 3600:
        return 900
    if seconds_to_kickoff > 1800:
        return 600
    return 300


def _near_miss(
    model_probability: float,
    calibrated_probability: float,
    odd: float,
    devig: float,
    settings: Settings,
) -> bool:
    decision = max(0.0, calibrated_probability - settings.probability_haircut)
    ev = decision * odd - 1.0
    edge = decision - devig
    return ev >= settings.min_ev - 0.03 or edge >= settings.min_edge - 0.02


def _event_from_prediction(
    prediction: dict[str, Any],
    *,
    quote: Any,
    decision_probability: float,
    expected_value: float,
    probability_edge: float,
    stake: float,
    now: datetime,
    linked_bet: dict[str, Any] | None,
) -> dict[str, Any]:
    event_id = f"{prediction['id']}:{now.astimezone(UTC).strftime('%Y%m%d%H%M')}"
    return {
        "id": event_id,
        "prediction_id": prediction["id"],
        "event_id": int(prediction["event_id"]),
        "market": prediction["market"],
        "market_display": prediction.get("market_display", prediction["market"]),
        "match": prediction.get("match"),
        "league": prediction.get("league"),
        "kickoff": prediction.get("kickoff"),
        "odd": round(quote.odd, 4),
        "opposite_odd": round(quote.opposite_odd, 4),
        "bookmaker_id": quote.bookmaker_id,
        "bookmaker": quote.bookmaker_name,
        "odds_captured_at": quote.captured_at.isoformat(),
        "model_probability": prediction.get("model_probability"),
        "calibrated_probability": prediction.get("calibrated_probability"),
        "decision_probability": round(decision_probability, 6),
        "probability_edge": round(probability_edge, 6),
        "expected_value": round(expected_value, 6),
        "stake": round(float(linked_bet.get("stake") if linked_bet else stake), 2),
        "signal_source": "INTRADAY_ALERT",
        "signal_sent_at": now.isoformat(),
        "linked_bet_id": linked_bet.get("id") if linked_bet else None,
        "status": "PENDING",
        "profit": 0.0,
        "closing_5m_odd": None,
        "closing_5m_opposite_odd": None,
        "closing_5m_market_probability_devig": None,
        "closing_5m_odds_captured_at": None,
    }


def _apply_linked_result(event: dict[str, Any], bet: dict[str, Any] | None) -> None:
    if not bet:
        return
    for key in (
        "status",
        "profit",
        "outcome",
        "closing_5m_odd",
        "closing_5m_opposite_odd",
        "closing_5m_market_probability_devig",
        "closing_5m_odds_captured_at",
    ):
        if bet.get(key) is not None:
            event[key] = bet[key]


def run_watchlist(settings: Settings, now: datetime | None = None) -> dict[str, int]:
    now_local = (now or datetime.now(settings.timezone)).astimezone(settings.timezone)
    now_utc = now_local.astimezone(UTC)
    root = settings.root
    state_path = root / STATE_FILE
    alerts_path = root / ALERT_FILE
    predictions = _load_list(settings.predictions_file)
    bets = BetStore(settings.bets_file).load()
    alerts = _load_list(alerts_path)
    state = _load_state(state_path)
    analytics = portfolio_analytics(
        bets, settings.initial_bank, today=now_local.date().isoformat()
    )
    linked = {
        (int(b.get("event_id")), str(b.get("market"))): b
        for b in bets
        if b.get("event_id") is not None
    }
    by_fixture: dict[int, list[dict[str, Any]]] = {}
    for prediction in predictions:
        try:
            fixture_id = int(prediction["event_id"])
            kickoff = datetime.fromisoformat(str(prediction["kickoff"]))
        except (KeyError, TypeError, ValueError):
            continue
        seconds = _seconds_to_kickoff(kickoff, now_utc)
        if not 300 < seconds <= settings.intraday_lookahead_hours * 3600:
            continue
        by_fixture.setdefault(fixture_id, []).append(prediction)

    scanned = 0
    alerts_sent = 0
    t5_captured = 0
    api = APIFootballClient(settings)

    for fixture_id, fixture_predictions in by_fixture.items():
        kickoff = datetime.fromisoformat(str(fixture_predictions[0]["kickoff"]))
        seconds = _seconds_to_kickoff(kickoff, now_utc)
        interval = cadence_seconds(seconds)
        fixture_state = state.get(str(fixture_id), {})
        last_scan_raw = fixture_state.get("last_scan_at")
        if last_scan_raw:
            try:
                elapsed = (
                    now_utc - datetime.fromisoformat(last_scan_raw).astimezone(UTC)
                ).total_seconds()
            except ValueError:
                elapsed = interval
            if elapsed < interval:
                continue

        try:
            quotes = extract_best_quotes(
                api.odds(fixture_id),
                bookmaker_priority=settings.bookmaker_priority,
                allow_any_bookmaker=settings.allow_any_bookmaker,
                captured_at=now_utc,
            )
        except (APIBudgetExceeded, APIError) as exc:
            print(f"⚠️ Watchlist fixture {fixture_id}: {exc}")
            if isinstance(exc, APIBudgetExceeded):
                break
            continue

        scanned += 1
        state[str(fixture_id)] = {
            "last_scan_at": now_utc.isoformat(),
            "cadence_seconds": interval,
        }
        strong_events: list[dict[str, Any]] = []
        for prediction in fixture_predictions:
            try:
                market = Market.parse(str(prediction["market"]))
            except (KeyError, TypeError, ValueError):
                continue
            quote = quotes.get(market)
            if quote is None or not (
                0.0 <= quote.overround <= settings.max_market_overround
            ):
                continue
            calibrated = float(
                prediction.get("calibrated_probability")
                or prediction.get("model_probability")
                or 0.0
            )
            decision = max(0.0, calibrated - settings.probability_haircut)
            ev = decision * quote.odd - 1.0
            edge = decision - quote.devig_probability
            linked_bet = linked.get((fixture_id, market.value))
            suggested_stake = (
                float(linked_bet.get("stake"))
                if linked_bet
                else kelly_stake(analytics.current_bank, decision, quote.odd, settings)
            )
            if not _near_miss(
                float(prediction.get("model_probability") or 0.0),
                calibrated,
                quote.odd,
                quote.devig_probability,
                settings,
            ):
                continue
            key = str(prediction["id"])
            previous = state.setdefault(key, {})
            was_strong = bool(previous.get("was_strong"))
            probe = {
                "id": linked_bet.get("id") if linked_bet else key,
                "event_id": fixture_id,
                "market": market.value,
                "market_display": prediction.get("market_display", market.value),
                "match": prediction.get("match"),
                "league": prediction.get("league"),
                "kickoff": prediction.get("kickoff"),
                "odd": quote.odd,
                "bookmaker": quote.bookmaker_name,
                "model_probability": prediction.get("model_probability"),
                "decision_probability": decision,
                "probability_edge": edge,
                "expected_value": ev,
                "stake": suggested_stake,
            }
            strong = is_strong_signal(probe, settings)
            previous["was_strong"] = strong
            previous["last_seen_at"] = now_utc.isoformat()
            if strong and not was_strong:
                event = _event_from_prediction(
                    prediction,
                    quote=quote,
                    decision_probability=decision,
                    expected_value=ev,
                    probability_edge=edge,
                    stake=suggested_stake,
                    now=now_local,
                    linked_bet=linked_bet,
                )
                alerts.append(event)
                strong_events.append(event)

            if strong and 120 <= seconds <= 480:
                event_matches = [a for a in alerts if a.get("prediction_id") == key]
                for event in event_matches:
                    if event.get("closing_5m_odd") is None:
                        event["closing_5m_odd"] = round(quote.odd, 4)
                        event["closing_5m_opposite_odd"] = round(quote.opposite_odd, 4)
                        event["closing_5m_market_probability_devig"] = round(
                            quote.devig_probability, 6
                        )
                        event["closing_5m_odds_captured_at"] = now_utc.isoformat()
                        t5_captured += 1

        if strong_events and settings.intraday_alert_enabled:
            result = SimpleNamespace(new_bets=tuple(strong_events))
            subject, html_body = build_strong_signal_email(result, settings, now_local)
            if send_strong_signal_email(subject, html_body, settings):
                alerts_sent += len(strong_events)

    for event in alerts:
        bet = linked.get((int(event.get("event_id", 0)), str(event.get("market", ""))))
        _apply_linked_result(event, bet)

    atomic_write_json(state_path, state)
    atomic_write_json(alerts_path, alerts[-1000:])
    return {
        "fixtures_scanned": scanned,
        "alerts_sent": alerts_sent,
        "t5_captured": t5_captured,
        "api_requests": api.request_count,
    }
