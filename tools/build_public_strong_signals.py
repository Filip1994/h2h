from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def build_public_strong_signals(root: Path = ROOT) -> list[dict[str, Any]]:
    previous = _load(root / "strong_signals.json")
    alerts = _load(root / "intraday_alerts.json")
    bets = [
        item
        for item in _load(root / "bets.json")
        if str(item.get("signal_source", "")) == "INTRADAY_ALERT"
    ]

    merged: dict[str, dict[str, Any]] = {}
    for item in previous + alerts + bets:
        key = str(item.get("id") or item.get("prediction_id") or item.get("event_id") or "")
        if not key:
            continue
        current = merged.setdefault(key, {})
        current.update(item)
        if item.get("status") in {"WIN", "LOSS"}:
            current["virtual_profit"] = item.get(
                "profit", item.get("virtual_profit", 0)
            )

    data = sorted(
        merged.values(),
        key=lambda item: str(
            item.get("signal_sent_at")
            or item.get("created_at")
            or item.get("date")
            or ""
        ),
    )
    (root / "strong_signals.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


if __name__ == "__main__":
    data = build_public_strong_signals()
    print(f"public strong signals: {len(data)}")
