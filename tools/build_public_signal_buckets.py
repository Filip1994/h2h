from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from build_near_miss_lifecycle import build as build_near_miss_lifecycle

from quantbot.strong_signal_bankroll import STRONG_SIGNAL_PORTFOLIO, portfolio

LEDGER_FILE = "strong_signal_ledger.json"
LEGACY_SETTLEMENTS_FILE = "strong_signal_legacy_settlements.json"
EVENT_FILE = "data/intraday_signal_events.jsonl"
LEGACY_H2H_KEYS = {
    "h2h_enabled",
    "h2h_available",
    "h2h_rate",
    "h2h_n",
    "h2h_effective_n",
    "h2h_history",
    "h2h_snapshot_id",
    "h2h_status",
    "h2h_error",
}
TERMINAL_STATUSES = {"WIN", "LOSS", "VOID", "REVIEW"}
NON_ACTIVE_STATUSES = {"SKIPPED", "SETTLED", "VOID", "REVIEW", "WIN", "LOSS"}


def load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows


def _canonical_key(item: dict[str, Any]) -> str:
    return str(
        item.get("id") or item.get("signal_id") or item.get("observation_id") or ""
    )


def _strip_legacy_h2h(row: dict[str, Any]) -> None:
    for key in LEGACY_H2H_KEYS:
        row.pop(key, None)


def _as_virtual(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row["virtual_portfolio"] = STRONG_SIGNAL_PORTFOLIO
    row["signal_class"] = "STRONG_SIGNAL"
    row["not_a_production_bet"] = True
    _strip_legacy_h2h(row)
    if row.get("virtual_settled") is True:
        status = str(
            row.get("virtual_status") or row.get("status") or "PENDING"
        ).upper()
        row["virtual_status"] = status
        row["status"] = status
        row["virtual_profit"] = float(row.get("virtual_profit") or 0.0)
        row["profit"] = row["virtual_profit"]
        return row
    source_status = str(row.get("status") or "PENDING").upper()
    if source_status in NON_ACTIVE_STATUSES and source_status != "PENDING":
        if source_status != "SKIPPED":
            row["production_status"] = row.get("status")
        if row.get("profit") not in (None, 0, 0.0):
            row["production_profit"] = row.get("profit")
        if row.get("result") is not None:
            row["production_result"] = row.get("result")
        if row.get("settled_at") is not None:
            row["production_settled_at"] = row.get("settled_at")
        if row.get("settlement_type") is not None:
            row["production_settlement_type"] = row.get("settlement_type")
        row["status"] = source_status
        row["profit"] = (
            0.0 if source_status == "SKIPPED" else float(row.get("profit") or 0.0)
        )
        row["virtual_profit"] = 0.0
        row["virtual_settled"] = False
        return row
    row["status"] = "PENDING"
    row["profit"] = 0.0
    row["virtual_profit"] = 0.0
    row["virtual_settled"] = False
    return row


def _legacy_settlement_map(root: Path) -> dict[str, dict[str, Any]]:
    rows = load_json(root / LEGACY_SETTLEMENTS_FILE)
    return {
        _canonical_key(row): row
        for row in rows
        if _canonical_key(row)
        and str(row.get("status") or "").upper() in TERMINAL_STATUSES
    }


def _restore_legacy_virtual_settlement(
    row: dict[str, Any], settlements: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if row.get("virtual_settled") is True:
        return row
    recovery = settlements.get(_canonical_key(row))
    if not recovery:
        return row
    status = str(recovery.get("status") or "PENDING").upper()
    if status not in TERMINAL_STATUSES:
        return row
    profit = float(recovery.get("profit") or 0.0)
    row.update(
        {
            "status": status,
            "virtual_status": status,
            "profit": profit,
            "virtual_profit": profit,
            "virtual_settled": True,
        }
    )
    if recovery.get("result") is not None:
        row["result"] = recovery["result"]
    if recovery.get("settled_at") is not None:
        row["settled_at"] = recovery["settled_at"]
        row["virtual_settled_at"] = recovery["settled_at"]
    row["settlement_type"] = "COUNTERFACTUAL_ALERT"
    return row


def load_or_migrate_ledger(root: Path) -> list[dict[str, Any]]:
    ledger_path = root / LEDGER_FILE
    settlements = _legacy_settlement_map(root)
    source = (
        load_json(ledger_path)
        if ledger_path.exists()
        else load_json(root / "strong_signals.json")
    )
    rows = [
        _restore_legacy_virtual_settlement(_as_virtual(x), settlements) for x in source
    ]
    if not ledger_path.exists():
        ledger_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return rows


def merge(
    items: list[dict[str, Any]], settlements: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _canonical_key(item)
        if not key:
            continue
        current = merged.setdefault(key, {})
        was_settled = current.get("virtual_settled") is True
        if was_settled and item.get("virtual_settled") is not True:
            protected = {
                k: current.get(k)
                for k in (
                    "virtual_settled",
                    "virtual_status",
                    "virtual_profit",
                    "status",
                    "profit",
                    "result",
                    "settled_at",
                    "settlement_type",
                    "virtual_settled_at",
                )
            }
            current.update(item)
            current.update({k: v for k, v in protected.items() if v is not None})
        else:
            current.update(item)
        merged[key] = _restore_legacy_virtual_settlement(
            _as_virtual(current), settlements
        )
    return sorted(
        merged.values(),
        key=lambda x: str(x.get("signal_sent_at") or x.get("captured_at") or ""),
    )


def _public_strong_event(
    row: dict[str, Any], source: dict[str, Any] | None = None
) -> dict[str, Any]:
    source = source or {}
    out = dict(row)
    for key in ("match", "league", "kickoff", "home_name", "away_name"):
        if out.get(key) is None and source.get(key) is not None:
            out[key] = source[key]
    out.setdefault("signal_id", out.get("event_id"))
    out.setdefault("signal_source", "INTRADAY_ALERT")
    out.setdefault("signal_type", "CLASSIFICATION_TRANSITION")
    out["signal_class"] = "STRONG_SIGNAL"
    out["virtual_portfolio"] = STRONG_SIGNAL_PORTFOLIO
    out["not_a_production_bet"] = True
    out.setdefault("virtual_profit", 0.0)
    out.setdefault("profit", 0.0)
    out.setdefault("virtual_settled", False)
    return out


def _legacy_near_miss_projection(
    observations: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    represented_ids: set[str],
) -> list[dict[str, Any]]:
    alerts_by_prediction = {
        str(row.get("prediction_id")): row
        for row in alerts
        if row.get("prediction_id") is not None
    }
    result: list[dict[str, Any]] = []
    for row in observations:
        if (
            str(row.get("signal_class") or row.get("signal_state") or "").upper()
            != "NEAR_MISS"
        ):
            continue
        observation_id = str(row.get("observation_id") or "")
        if observation_id and observation_id in represented_ids:
            continue
        alert = alerts_by_prediction.get(str(row.get("prediction_id") or ""), {})
        match = row.get("match") or alert.get("match")
        home = row.get("home_name") or alert.get("home_name")
        away = row.get("away_name") or alert.get("away_name")
        if not match and home and away:
            match = f"{home} vs {away}"
        result.append(
            {
                "schema_version": 3,
                "id": observation_id
                or f"near:{row.get('prediction_id')}:{row.get('captured_at')}",
                "signal_class": "NEAR_MISS",
                "signal_type": "NEAR_MISS_OBSERVATION",
                "not_a_production_bet": True,
                "prediction_id": row.get("prediction_id"),
                "event_id": row.get("fixture_id") or row.get("event_id"),
                "fixture_id": row.get("fixture_id") or row.get("event_id"),
                "market": row.get("market"),
                "selection": row.get("selection") or row.get("market"),
                "market_display": row.get("market_display") or row.get("market"),
                "home_name": home,
                "away_name": away,
                "match": match,
                "league": row.get("league") or alert.get("league"),
                "kickoff": row.get("kickoff") or alert.get("kickoff"),
                "bookmaker_id": row.get("bookmaker_id") or alert.get("bookmaker_id"),
                "bookmaker": row.get("bookmaker") or alert.get("bookmaker"),
                "opening_odd": None,
                "opening_opposite_odd": None,
                "opening_captured_at": None,
                "opening_observation_id": None,
                "odd": row.get("odd"),
                "opposite_odd": row.get("opposite_odd"),
                "near_miss_odd": row.get("odd"),
                "near_miss_opposite_odd": row.get("opposite_odd"),
                "near_miss_captured_at": row.get("captured_at"),
                "near_miss_observation_id": observation_id or None,
                "pick_odd": None,
                "pick_opposite_odd": None,
                "pick_captured_at": None,
                "pick_observation_id": None,
                "promoted_to_signal_id": None,
                "closing_odd": None,
                "closing_opposite_odd": None,
                "closing_captured_at": None,
                "closing_observation_id": None,
                "clv_odds_pct": None,
                "model_probability": row.get("model_probability"),
                "calibrated_probability": row.get("calibrated_probability"),
                "decision_probability": row.get("decision_probability"),
                "probability_edge": row.get("probability_edge"),
                "expected_value": row.get("expected_value"),
                "stake": row.get("stake", row.get("virtual_stake", 0)),
                "near_miss_reason": row.get("near_miss_reason"),
                "transition_history": [],
                "status": "PENDING",
                "result": None,
                "settled_at": None,
                "settlement_type": None,
                "virtual_portfolio": "NEAR_MISS_OBSERVATIONAL",
                "virtual_settled": False,
                "profit": 0.0,
                "virtual_profit": 0.0,
                "signal_sent_at": row.get("captured_at"),
                "source_observation_ids": [observation_id] if observation_id else [],
                "production_linked_bet_id": None,
            }
        )
    return result


def _publishable_near_miss(row: dict[str, Any]) -> bool:
    return all(
        str(row.get(field) or "").strip()
        for field in (
            "prediction_id",
            "fixture_id",
            "market",
            "selection",
            "home_name",
            "away_name",
            "match",
            "league",
            "kickoff",
            "bookmaker_id",
            "bookmaker",
        )
    )


def build(root: Path = ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    near = [
        row for row in build_near_miss_lifecycle(root) if _publishable_near_miss(row)
    ]
    (root / "near_misses.json").write_text(
        json.dumps(near, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ledger = load_or_migrate_ledger(root)
    settlements = _legacy_settlement_map(root)
    alerts = load_json(root / "intraday_alerts.json")
    observations = load_jsonl(root / "data" / "market_timing_snapshots.jsonl")
    signal_events = load_jsonl(root / EVENT_FILE)
    represented_ids = {
        str(observation_id)
        for row in near
        for observation_id in row.get("source_observation_ids", [])
        if observation_id
    }
    represented_ids.update(
        str(row.get("near_miss_observation_id"))
        for row in near
        if row.get("near_miss_observation_id")
    )
    near.extend(
        row
        for row in _legacy_near_miss_projection(observations, alerts, represented_ids)
        if _publishable_near_miss(row)
    )
    near.sort(
        key=lambda row: str(row.get("signal_sent_at") or row.get("kickoff") or "")
    )
    (root / "near_misses.json").write_text(
        json.dumps(near, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    observation_lookup: dict[str, dict[str, Any]] = {}
    for observation in observations:
        key = str(observation.get("prediction_id") or "")
        if key:
            observation_lookup[key] = observation
    strong_updates: list[dict[str, Any]] = []
    for alert in alerts:
        if str(alert.get("signal_class") or "").upper() in {"STRONG_SIGNAL", "STRONG"}:
            strong_updates.append(
                _public_strong_event(
                    alert, observation_lookup.get(str(alert.get("prediction_id") or ""))
                )
            )
    for event in signal_events:
        if str(event.get("signal_class") or "").upper() != "STRONG_SIGNAL":
            continue
        if not str(event.get("transition") or "").endswith("->STRONG_SIGNAL"):
            continue
        strong_updates.append(
            _public_strong_event(
                event, observation_lookup.get(str(event.get("prediction_id") or ""))
            )
        )
    strong = merge(ledger + strong_updates, settlements)
    (root / LEDGER_FILE).write_text(
        json.dumps(strong, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "strong_signals.json").write_text(
        json.dumps(strong, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metrics = portfolio(strong)
    (root / "strong_signals_portfolio.json").write_text(
        json.dumps(
            {
                "portfolio": STRONG_SIGNAL_PORTFOLIO,
                "production": False,
                "not_a_production_bet": True,
                "initial_bank": metrics.initial_bank,
                "current_bank": metrics.current_bank,
                "total_profit": metrics.total_profit,
                "total_stake": metrics.total_stake,
                "roi": metrics.roi,
                "win_rate": metrics.win_rate,
                "completed_count": metrics.completed_count,
                "open_stake": metrics.open_stake,
                "current_drawdown": metrics.current_drawdown,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return strong, near


if __name__ == "__main__":
    strong, near = build()
    print(f"public strong signals: {len(strong)}")
    print(f"public near misses: {len(near)}")
