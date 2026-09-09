from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"WIN", "LOSS", "VOID", "REVIEW", "SKIPPED"}


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


def merge(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("id") or item.get("signal_id") or item.get("observation_id") or "")
        if not key:
            continue
        merged.setdefault(key, {}).update(item)
    return sorted(
        merged.values(),
        key=lambda item: str(item.get("signal_sent_at") or item.get("captured_at") or ""),
    )


def observation_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("observation_id") or f"{row.get('prediction_id')}:{row.get('captured_at')}",
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


def build(root: Path = ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    old_strong = load_json(root / "strong_signals.json")
    alerts = load_json(root / "intraday_alerts.json")
    bets = [x for x in load_json(root / "bets.json") if str(x.get("signal_source")) == "INTRADAY_ALERT"]
    observations = load_jsonl(root / "data" / "market_timing_snapshots.jsonl")

    strong_candidates = [
        x for x in old_strong + alerts + bets
        if str(x.get("signal_class") or "").upper() in {"STRONG_SIGNAL", "STRONG"}
        or ("signal_class" not in x and x in old_strong)
    ]
    strong = merge(strong_candidates)
    near = merge([
        observation_public(x)
        for x in observations
        if str(x.get("signal_class") or x.get("signal_state") or "").upper() == "NEAR_MISS"
    ])
    (root / "strong_signals.json").write_text(
        json.dumps(strong, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "near_misses.json").write_text(
        json.dumps(near, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return strong, near


if __name__ == "__main__":
    strong, near = build()
    print(f"public strong signals: {len(strong)}")
    print(f"public near misses: {len(near)}")
