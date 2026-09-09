from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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
        return rows
    return rows


def _canonical_key(item: dict[str, Any]) -> str:
    return str(
        item.get("id") or item.get("signal_id") or item.get("observation_id") or ""
    )


def _strip_legacy_h2h(row: dict[str, Any]) -> None:
    for key in LEGACY_H2H_KEYS:
        row.pop(key, None)


def _as_virtual(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a signal without importing Production settlement into it."""
    row = dict(item)
    row["virtual_portfolio"] = STRONG_SIGNAL_PORTFOLIO
    row["signal_class"] = "STRONG_SIGNAL"
    row["not_a_production_bet"] = True
    _strip_legacy_h2h(row)

    if row.get("virtual_settled") is True:
        virtual_status = str(
            row.get("virtual_status") or row.get("status") or "PENDING"
        ).upper()
        row["virtual_status"] = virtual_status
        row["status"] = virtual_status
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

    if row.get("status") not in (None, "PENDING"):
        row["production_status"] = row.get("status")
    if row.get("profit") not in (None, 0, 0.0):
        row["production_profit"] = row.get("profit")
    if row.get("result") is not None:
        row["production_result"] = row.get("result")
    if row.get("settled_at") is not None:
        row["production_settled_at"] = row.get("settled_at")
    if row.get("settlement_type") is not None:
        row["production_settlement_type"] = row.get("settlement_type")
    for key in (
        "status",
        "profit",
        "result",
        "settled_at",
        "settlement_type",
        "virtual_profit",
    ):
        row.pop(key, None)
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
    """Recover the frozen historical Strong Signal ledger snapshot."""
    if row.get("virtual_settled") is True:
        return row
    recovery = settlements.get(_canonical_key(row))
    if not recovery:
        return row
    status = str(recovery.get("status") or "PENDING").upper()
    if status not in TERMINAL_STATUSES:
        return row
    profit = float(recovery.get("profit") or 0.0)
    row["status"] = status
    row["virtual_status"] = status
    row["profit"] = profit
    row["virtual_profit"] = profit
    row["virtual_settled"] = True
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
    if ledger_path.exists():
        rows = [_as_virtual(x) for x in load_json(ledger_path)]
    else:
        legacy = load_json(root / "strong_signals.json")
        rows = [_as_virtual(x) for x in legacy]
    recovered = [_restore_legacy_virtual_settlement(row, settlements) for row in rows]
    if not ledger_path.exists():
        ledger_path.write_text(
            json.dumps(recovered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return recovered


def merge(
    items: list[dict[str, Any]], settlements: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _canonical_key(item)
        if not key:
            continue
        current = merged.setdefault(key, {})
        was_virtual_settled = current.get("virtual_settled") is True
        if was_virtual_settled and item.get("virtual_settled") is not True:
            protected = {
                field: current.get(field)
                for field in (
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
        current = _as_virtual(current)
        current = _restore_legacy_virtual_settlement(current, settlements)
        merged[key] = current
    return sorted(
        merged.values(),
        key=lambda item: str(
            item.get("signal_sent_at") or item.get("captured_at") or ""
        ),
    )


def observation_public(
    row: dict[str, Any], source: dict[str, Any] | None = None
) -> dict[str, Any]:
    source = source or {}
    home = (
        row.get("home_name")
        or row.get("home_team")
        or row.get("home")
        or row.get("home_team_name")
        or source.get("home_name")
        or source.get("home_team")
        or source.get("home")
    )
    away = (
        row.get("away_name")
        or row.get("away_team")
        or row.get("away")
        or row.get("away_team_name")
        or source.get("away_name")
        or source.get("away_team")
        or source.get("away")
    )
    match = (
        row.get("match")
        or source.get("match")
        or (f"{home} vs {away}" if home and away else None)
    )
    return {
        "id": row.get("observation_id")
        or f"{row.get('prediction_id')}:{row.get('captured_at')}",
        "prediction_id": row.get("prediction_id"),
        "event_id": row.get("fixture_id"),
        "market": row.get("market"),
        "market_display": row.get("market_display", row.get("market")),
        "match": match,
        "home_name": home,
        "away_name": away,
        "league": (
            row.get("league")
            or row.get("league_name")
            or source.get("league")
            or source.get("league_name")
        ),
        "kickoff": row.get("kickoff") or source.get("kickoff"),
        "odd": row.get("odd"),
        "opposite_odd": row.get("opposite_odd"),
        "bookmaker_id": row.get("bookmaker_id") or source.get("bookmaker_id"),
        "bookmaker": row.get("bookmaker") or source.get("bookmaker"),
        "odds_captured_at": row.get("captured_at"),
        "model_probability": row.get("model_probability"),
        "calibrated_probability": row.get("calibrated_probability"),
        "decision_probability": row.get("decision_probability"),
        "probability_edge": row.get("probability_edge"),
        "expected_value": row.get("expected_value"),
        "stake": row.get("stake", 0),
        "signal_source": "INTRADAY_OBSERVATION",
        "signal_class": "NEAR_MISS",
        "near_miss_reason": row.get("near_miss_reason"),
        "signal_sent_at": row.get("captured_at"),
        "status": "PENDING",
        "profit": 0.0,
    }


def signal_event_public(
    row: dict[str, Any], source: dict[str, Any] | None = None
) -> dict[str, Any]:
    source = source or {}
    return {
        "id": row.get("event_id"),
        "signal_id": row.get("event_id"),
        "prediction_id": row.get("prediction_id"),
        "event_id": row.get("fixture_id"),
        "market": row.get("market"),
        "market_display": row.get("market_display", row.get("market")),
        "match": row.get("match") or source.get("match"),
        "league": row.get("league") or source.get("league"),
        "kickoff": row.get("kickoff") or source.get("kickoff"),
        "odd": row.get("odd"),
        "opposite_odd": row.get("opposite_odd"),
        "bookmaker_id": row.get("bookmaker_id"),
        "bookmaker": row.get("bookmaker"),
        "odds_captured_at": row.get("captured_at"),
        "model_probability": row.get("model_probability"),
        "calibrated_probability": row.get("calibrated_probability"),
        "decision_probability": row.get("decision_probability"),
        "probability_edge": row.get("probability_edge"),
        "expected_value": row.get("expected_value"),
        "stake": row.get("stake", 0),
        "signal_source": "INTRADAY_ALERT",
        "signal_type": "CLASSIFICATION_TRANSITION",
        "signal_class": "STRONG_SIGNAL",
        "virtual_portfolio": STRONG_SIGNAL_PORTFOLIO,
        "near_miss_reason": None,
        "signal_sent_at": row.get("captured_at"),
        "linked_bet_id": None,
        "status": "PENDING",
        "profit": 0.0,
        "virtual_profit": 0.0,
        "virtual_settled": False,
        "source_transition": row.get("transition"),
        "source_event_id": row.get("event_id"),
    }


def build(root: Path = ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger = load_or_migrate_ledger(root)
    settlements = _legacy_settlement_map(root)
    alerts = load_json(root / "intraday_alerts.json")
    observations = load_jsonl(root / "data" / "market_timing_snapshots.jsonl")
    signal_events = load_jsonl(root / EVENT_FILE)

    alert_lookup: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        for key in (
            alert.get("prediction_id"),
            alert.get("event_id"),
            alert.get("fixture_id"),
        ):
            if key is not None and str(key):
                alert_lookup[str(key)] = alert

    observation_lookup: dict[str, dict[str, Any]] = {}
    for observation in observations:
        for key in (
            observation.get("prediction_id"),
            observation.get("fixture_id"),
            observation.get("event_id"),
        ):
            if key is not None and str(key):
                observation_lookup[str(key)] = observation

    strong_updates = [
        x
        for x in alerts
        if str(x.get("signal_class") or "").upper() in {"STRONG_SIGNAL", "STRONG"}
    ]

    # A Strong Signal is an independent virtual observation.  It must not
    # disappear merely because the same prediction is also linked to a
    # Production bet.  watchlist.py records every classification transition
    # durably in intraday_signal_events.jsonl; INITIAL/NEAR_MISS ->
    # STRONG_SIGNAL transitions are therefore the authoritative fallback for
    # persistence when no alert email/event was emitted.
    for event in signal_events:
        if str(event.get("signal_class") or "").upper() != "STRONG_SIGNAL":
            continue
        transition = str(event.get("transition") or "")
        if not transition.endswith("->STRONG_SIGNAL"):
            continue
        source = observation_lookup.get(str(event.get("prediction_id") or "")) or alert_lookup.get(
            str(event.get("prediction_id") or "")
        )
        strong_updates.append(signal_event_public(event, source))

    strong = merge(ledger + strong_updates, settlements)
    (root / LEDGER_FILE).write_text(
        json.dumps(strong, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    near = []
    for observation in observations:
        if (
            str(
                observation.get("signal_class") or observation.get("signal_state") or ""
            ).upper()
            != "NEAR_MISS"
        ):
            continue
        source = alert_lookup.get(
            str(observation.get("prediction_id") or "")
        ) or alert_lookup.get(
            str(observation.get("fixture_id") or observation.get("event_id") or "")
        )
        near.append(observation_public(observation, source))
    (root / "strong_signals.json").write_text(
        json.dumps(strong, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "near_misses.json").write_text(
        json.dumps(near, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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