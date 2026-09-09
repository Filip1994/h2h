from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.quantbot.strong_signal_bankroll import STRONG_SIGNAL_PORTFOLIO, portfolio

ROOT = Path(__file__).resolve().parents[1]
LEDGER_FILE = "strong_signal_ledger.json"
TERMINAL = {"WIN", "LOSS", "VOID", "REVIEW"}


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


def _as_virtual(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a signal into the isolated virtual portfolio contract."""
    row = dict(item)
    row["virtual_portfolio"] = STRONG_SIGNAL_PORTFOLIO
    row["signal_class"] = "STRONG_SIGNAL"
    row["not_a_production_bet"] = True

    if not row.get("virtual_settled"):
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


def load_or_migrate_ledger(root: Path) -> list[dict[str, Any]]:
    ledger_path = root / LEDGER_FILE
    if ledger_path.exists():
        return [_as_virtual(x) for x in load_json(ledger_path)]

    legacy = load_json(root / "strong_signals.json")
    migrated = [_as_virtual(x) for x in legacy]
    ledger_path.write_text(
        json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return migrated


def merge(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _canonical_key(item)
        if not key:
            continue
        current = merged.setdefault(key, {})
        current.update(item)
        merged[key] = _as_virtual(current)
    return sorted(
        merged.values(),
        key=lambda item: str(
            item.get("signal_sent_at") or item.get("captured_at") or ""
        ),
    )


def observation_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("observation_id")
        or f"{row.get('prediction_id')}:{row.get('captured_at')}",
        "prediction_id": row.get("prediction_id"),
        "event_id": row.get("fixture_id"),
        "market": row.get("market"),
        "market_display": row.get("market_display", row.get("market")),
        "match": row.get("match"),
        "league": row.get("league"),
        "kickoff": row.get("kickoff"),
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
        "signal_source": "INTRADAY_OBSERVATION",
        "signal_class": "NEAR_MISS",
        "near_miss_reason": row.get("near_miss_reason"),
        "signal_sent_at": row.get("captured_at"),
        "status": "PENDING",
        "profit": 0.0,
    }


def build(
    root: Path = ROOT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger = load_or_migrate_ledger(root)
    alerts = load_json(root / "intraday_alerts.json")
    observations = load_jsonl(root / "data" / "market_timing_snapshots.jsonl")

    strong_updates = [
        x
        for x in alerts
        if str(x.get("signal_class") or "").upper()
        in {"STRONG_SIGNAL", "STRONG"}
    ]
    strong = merge(ledger + strong_updates)
    (root / LEDGER_FILE).write_text(
        json.dumps(strong, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    near = [
        observation_public(x)
        for x in observations
        if str(x.get("signal_class") or x.get("signal_state") or "").upper()
        == "NEAR_MISS"
    ]
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
