from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, default: Any):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def parse_dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def selection_of(row: dict[str, Any]) -> str:
    return str(row.get("selection") or row.get("market") or "")


def lifecycle_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("prediction_id") or ""),
        str(row.get("fixture_id") or row.get("event_id") or ""),
        str(row.get("market") or ""),
        selection_of(row),
        str(row.get("bookmaker_id") or ""),
    )


def exact_identity(
    row: dict[str, Any],
    *,
    prediction_id: str,
    fixture: str,
    market: str,
    selection: str,
    bookmaker: str,
) -> bool:
    return (
        str(row.get("prediction_id") or "") == prediction_id
        and str(row.get("fixture_id") or row.get("event_id") or "") == fixture
        and str(row.get("market") or "") == market
        and selection_of(row) == selection
        and str(row.get("bookmaker_id") or "") == bookmaker
    )


def prediction_identity(prediction: dict[str, Any]) -> dict[str, Any]:
    home = prediction.get("home_name") or prediction.get("home_team") or prediction.get("home")
    away = prediction.get("away_name") or prediction.get("away_team") or prediction.get("away")
    return {
        "home_name": home,
        "away_name": away,
        "match": prediction.get("match") or (f"{home} vs {away}" if home and away else None),
        "league": prediction.get("league") or prediction.get("league_name"),
        "kickoff": prediction.get("kickoff"),
    }


def _capture_time(row: dict[str, Any]) -> datetime | None:
    return parse_dt(row.get("captured_at") or row.get("odds_captured_at") or row.get("signal_sent_at"))


def _event_sort_key(row: dict[str, Any]) -> datetime:
    return _capture_time(row) or datetime.min.replace(tzinfo=UTC)


def _settlement_from_prediction(prediction: dict[str, Any]) -> tuple[str | None, str | None, str | None, bool]:
    status = str(prediction.get("status") or "").upper()
    result = prediction.get("result")
    settled_at = prediction.get("settled_at")
    if status in {"WIN", "LOSS", "VOID", "REVIEW"}:
        return status, result, settled_at, True
    if status == "SETTLED" and prediction.get("outcome") is not None:
        result = result or str(prediction.get("outcome"))
        return ("WIN" if bool(prediction.get("outcome")) else "LOSS"), result, settled_at, True
    return None, result, settled_at, False


def build(root: Path = ROOT, now: datetime | None = None) -> list[dict[str, Any]]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    predictions = load_json(root / "predictions.json", [])
    predictions = predictions if isinstance(predictions, list) else []
    prediction_by_id = {
        str(item.get("id")): item
        for item in predictions
        if isinstance(item, dict) and item.get("id")
    }
    observations = load_jsonl(root / "data" / "market_timing_snapshots.jsonl")
    canonical = load_jsonl(root / "data" / "odds_snapshots.jsonl")
    transitions = load_jsonl(root / "data" / "intraday_signal_events.jsonl")
    alerts = load_json(root / "intraday_alerts.json", [])
    alerts = alerts if isinstance(alerts, list) else []
    bets = load_json(root / "bets.json", [])
    bets = bets if isinstance(bets, list) else []
    existing = load_json(root / "near_misses.json", [])
    existing = existing if isinstance(existing, list) else []

    candidates = [
        row for row in observations
        if str(row.get("signal_class") or row.get("signal_state") or "").upper() == "NEAR_MISS"
    ]
    candidates.extend(row for row in existing if isinstance(row, dict))
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in candidates:
        key = lifecycle_key(row)
        if all(key):
            groups.setdefault(key, []).append(row)

    result: list[dict[str, Any]] = []
    for key, items in groups.items():
        prediction_id, fixture, market, selection, bookmaker = key
        prediction = prediction_by_id.get(prediction_id, {})
        identity = prediction_identity(prediction)
        first = min(items, key=_event_sort_key)
        latest = max(items, key=_event_sort_key)
        for field in ("home_name", "away_name", "match", "league", "kickoff"):
            if not identity.get(field):
                identity[field] = latest.get(field) or first.get(field)
        kickoff = parse_dt(identity.get("kickoff") or latest.get("kickoff"))
        near_at = _capture_time(latest)

        exact_alerts = [
            row for row in alerts
            if isinstance(row, dict)
            and str(row.get("signal_class") or "").upper() == "STRONG_SIGNAL"
            and exact_identity(
                row,
                prediction_id=prediction_id,
                fixture=fixture,
                market=market,
                selection=selection,
                bookmaker=bookmaker,
            )
        ]
        exact_bets = [
            row for row in bets
            if isinstance(row, dict)
            and exact_identity(
                row,
                prediction_id=prediction_id,
                fixture=fixture,
                market=market,
                selection=selection,
                bookmaker=bookmaker,
            )
        ]
        promotions = exact_alerts or [
            row for row in exact_bets
            if str(row.get("signal_source") or "").upper() == "INTRADAY_ALERT"
        ]
        pick = min(promotions, key=_event_sort_key) if promotions else None
        pick_at = _capture_time(pick or {})

        same_canonical = [
            row for row in canonical
            if exact_identity(
                row,
                prediction_id=prediction_id,
                fixture=fixture,
                market=market,
                selection=selection,
                bookmaker=bookmaker,
            )
            and _capture_time(row)
            and kickoff
            and _capture_time(row) < kickoff
        ]
        pre_pick = [row for row in same_canonical if pick_at is None or _capture_time(row) < pick_at]
        opening_pool = pre_pick or same_canonical
        opening = min(opening_pool, key=_event_sort_key) if opening_pool else None
        t5 = [
            row for row in same_canonical
            if str(row.get("snapshot_type") or "").upper() == "T5"
        ]
        closing = max(t5, key=_event_sort_key) if t5 else None

        exact_transitions = [
            row for row in transitions
            if isinstance(row, dict)
            and exact_identity(
                row,
                prediction_id=prediction_id,
                fixture=fixture,
                market=market,
                selection=selection,
                bookmaker=bookmaker,
            )
        ]
        exact_transitions.sort(key=_event_sort_key)
        transition_history = [
            {
                "event_id": item.get("event_id"),
                "captured_at": item.get("captured_at"),
                "transition": item.get("transition"),
                "signal_class": item.get("signal_class"),
                "previous_signal_class": item.get("previous_signal_class"),
                "reason": item.get("near_miss_reason"),
                "odd": item.get("odd"),
                "opposite_odd": item.get("opposite_odd"),
                "expected_value": item.get("expected_value"),
                "probability_edge": item.get("probability_edge"),
                "decision_probability": item.get("decision_probability"),
                "stake": item.get("stake"),
            }
            for item in exact_transitions
        ]

        settlement_status, settlement_result, settlement_at, settled = _settlement_from_prediction(prediction)
        promoted = bool(promotions)
        if settled:
            status = settlement_status
            settlement_type = "OBSERVATIONAL_VIRTUAL"
            virtual_settled = True
        elif promoted and kickoff and now >= kickoff:
            status = "SETTLEMENT_PENDING"
            settlement_type = None
            virtual_settled = False
        elif promoted:
            status = "PROMOTED"
            settlement_type = None
            virtual_settled = False
        elif kickoff and now >= kickoff:
            status = "EXPIRED"
            settlement_type = "OBSERVATIONAL_EXPIRED"
            virtual_settled = False
        else:
            status = "PENDING"
            settlement_type = None
            virtual_settled = False

        event_id_value: int | str = fixture
        try:
            event_id_value = int(fixture)
        except ValueError:
            pass
        bookmaker_value: int | str = bookmaker
        try:
            bookmaker_value = int(bookmaker)
        except ValueError:
            pass

        row = {
            "schema_version": 3,
            "id": f"near:{prediction_id}:{fixture}:{market}:{selection}:{bookmaker}",
            "signal_class": "NEAR_MISS",
            "signal_type": "NEAR_MISS_OBSERVATION",
            "not_a_production_bet": True,
            "prediction_id": prediction_id,
            "event_id": event_id_value,
            "fixture_id": event_id_value,
            "market": market,
            "selection": selection,
            "market_display": latest.get("market_display") or market,
            "home_name": identity.get("home_name"),
            "away_name": identity.get("away_name"),
            "match": identity.get("match"),
            "league": identity.get("league"),
            "kickoff": identity.get("kickoff"),
            "bookmaker_id": bookmaker_value,
            "bookmaker": latest.get("bookmaker") or first.get("bookmaker"),
            "opening_odd": opening.get("odd") if opening else None,
            "opening_opposite_odd": opening.get("opposite_odd") if opening else None,
            "opening_captured_at": opening.get("odds_captured_at") if opening else None,
            "opening_observation_id": opening.get("observation_id") if opening else None,
            "odd": latest.get("odd"),
            "opposite_odd": latest.get("opposite_odd"),
            "near_miss_odd": latest.get("odd"),
            "near_miss_opposite_odd": latest.get("opposite_odd"),
            "near_miss_captured_at": near_at.isoformat() if near_at else None,
            "near_miss_observation_id": latest.get("observation_id"),
            "pick_odd": pick.get("odd") if pick else None,
            "pick_opposite_odd": pick.get("opposite_odd") if pick else None,
            "pick_captured_at": pick_at.isoformat() if pick_at else None,
            "pick_observation_id": pick.get("signal_id") if pick else None,
            "promoted_to_signal_id": (pick.get("signal_id") or pick.get("id")) if pick else None,
            "closing_odd": closing.get("odd") if closing else None,
            "closing_opposite_odd": closing.get("opposite_odd") if closing else None,
            "closing_captured_at": closing.get("odds_captured_at") if closing else None,
            "closing_observation_id": closing.get("observation_id") if closing else None,
            "clv_odds_pct": None,
            "model_probability": latest.get("model_probability"),
            "calibrated_probability": latest.get("calibrated_probability"),
            "decision_probability": latest.get("decision_probability"),
            "probability_edge": latest.get("probability_edge"),
            "expected_value": latest.get("expected_value"),
            "stake": latest.get("stake", latest.get("virtual_stake", 0)),
            "near_miss_reason": latest.get("near_miss_reason"),
            "transition_history": transition_history,
            "status": status,
            "result": settlement_result,
            "settled_at": settlement_at,
            "settlement_type": settlement_type,
            "virtual_portfolio": "NEAR_MISS_OBSERVATIONAL",
            "virtual_settled": virtual_settled,
            "profit": 0.0,
            "virtual_profit": 0.0,
            "signal_sent_at": near_at.isoformat() if near_at else None,
            "source_observation_ids": [
                item.get("observation_id")
                for item in items
                if item.get("observation_id")
            ],
            "production_linked_bet_id": None,
        }
        if settled:
            row["settlement_source"] = "prediction_lifecycle"
        if exact_bets:
            bet = min(exact_bets, key=_event_sort_key)
            row["production_linked_bet_id"] = bet.get("id")
            if bet.get("result") is not None:
                row["production_result"] = bet.get("result")
            if bet.get("status") not in (None, "PENDING"):
                row["production_status"] = bet.get("status")
            if bet.get("settled_at") is not None:
                row["production_settled_at"] = bet.get("settled_at")
        result.append(row)

    result.sort(key=lambda item: str(item.get("signal_sent_at") or item.get("kickoff") or ""))
    (root / "near_misses.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    rows = build()
    print(
        json.dumps(
            {
                "near_misses": len(rows),
                "active": sum(row["status"] in {"PENDING", "PROMOTED", "SETTLEMENT_PENDING"} for row in rows),
                "expired": sum(row["status"] == "EXPIRED" for row in rows),
                "promoted": sum(row["status"] == "PROMOTED" for row in rows),
                "settled": sum(row["virtual_settled"] for row in rows),
            },
            ensure_ascii=False,
        )
    )
