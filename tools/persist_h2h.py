from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from quantbot.config import Settings
from quantbot.h2h_telemetry import H2HOutcomeStore


def load_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def parse_score(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    try:
        home, away = value.split(":", 1)
        return int(home), int(away)
    except ValueError:
        return None


def main() -> int:
    settings = Settings.from_env()
    predictions = load_list(settings.predictions_file)
    alerts_path = settings.root / "intraday_alerts.json"
    alerts = load_list(alerts_path)
    by_prediction = {
        str(item.get("id")): item for item in predictions if item.get("id")
    }

    alert_changed = False
    signal_count = 0
    linked_signal_count = 0
    for event in alerts:
        prediction_id = str(event.get("prediction_id") or "")
        prediction = by_prediction.get(prediction_id)
        if not prediction:
            continue
        signal_count += 1
        snapshot_id = prediction.get("h2h_snapshot_id")
        if snapshot_id and event.get("h2h_snapshot_id") != snapshot_id:
            event["h2h_snapshot_id"] = snapshot_id
            event["h2h_status"] = prediction.get("h2h_status")
            event["h2h_available"] = prediction.get("h2h_available", False)
            alert_changed = True
        if event.get("h2h_snapshot_id"):
            linked_signal_count += 1

    if alert_changed:
        alerts_path.write_text(
            json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    outcomes = H2HOutcomeStore(settings.root)
    outcome_count = 0
    for prediction in predictions:
        snapshot_id = prediction.get("h2h_snapshot_id")
        if not snapshot_id:
            continue
        score = parse_score(prediction.get("result"))
        status = str(prediction.get("status", "")).upper()
        if score is None or status not in {"SETTLED", "WIN", "LOSS"}:
            continue
        captured_at = datetime.now(UTC)
        if prediction.get("settled_at"):
            try:
                captured_at = datetime.fromisoformat(
                    str(prediction["settled_at"])
                ).astimezone(UTC)
            except ValueError:
                pass
        if outcomes.append(
            snapshot_id=str(snapshot_id),
            fixture_id=int(prediction["event_id"]),
            home_goals=score[0],
            away_goals=score[1],
            captured_at=captured_at,
        ):
            outcome_count += 1

    print(
        f"H2H telemetry: predictions={len(predictions)} "
        f"snapshots_linked={sum(bool(p.get('h2h_snapshot_id')) for p in predictions)} "
        f"signals={signal_count} signals_linked={linked_signal_count} "
        f"outcomes_added={outcome_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
