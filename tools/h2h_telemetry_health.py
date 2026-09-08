from __future__ import annotations

import json
from pathlib import Path


def load_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    predictions = load_list(root / "predictions.json")
    alerts = load_list(root / "intraday_alerts.json")
    snapshots = []
    path = root / "data" / "h2h_snapshots.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                snapshots.append(item)
    selected = [p for p in predictions if p.get("selected") is True]
    signals = [
        a
        for a in alerts
        if a.get("signal_type") in {"NEW_OPPORTUNITY", "SIGNAL_UPDATE"}
    ]
    linked_predictions = [p for p in predictions if p.get("h2h_snapshot_id")]
    available = [p for p in predictions if p.get("h2h_available") is True]
    api_errors = [p for p in predictions if p.get("h2h_status") == "API_ERROR"]
    print("H2H RESEARCH COVERAGE")
    print(f"Predictions: {len(predictions)}")
    print(f"H2H linked: {len(linked_predictions)}")
    print(f"H2H available: {len(available)}")
    print(f"API errors: {len(api_errors)}")
    print(f"Selected: {len(selected)}")
    print(f"Selected + H2H: {sum(bool(p.get('h2h_snapshot_id')) for p in selected)}")
    print(f"Signals: {len(signals)}")
    print(f"Signals + H2H: {sum(bool(a.get('h2h_snapshot_id')) for a in signals)}")
    print(f"Canonical snapshots: {len(snapshots)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
