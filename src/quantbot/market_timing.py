from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_FILE = "data/market_timing_snapshots.jsonl"
METRICS_FILE = "market_timing_metrics.json"
SCHEMA_VERSION = 1


def _observation_id(snapshot: dict[str, Any]) -> str:
    identity = {
        "fixture_id": snapshot.get("fixture_id"),
        "prediction_id": snapshot.get("prediction_id"),
        "market": snapshot.get("market"),
        "bookmaker_id": snapshot.get("bookmaker_id"),
        "captured_at": snapshot.get("captured_at"),
        "odd": snapshot.get("odd"),
        "opposite_odd": snapshot.get("opposite_odd"),
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_snapshot(
    *,
    fixture_id: int,
    prediction: dict[str, Any],
    quote: Any,
    decision_probability: float,
    expected_value: float,
    probability_edge: float,
    seconds_to_kickoff: float,
    signal_state: str,
    captured_at: datetime,
) -> dict[str, Any]:
    kickoff = datetime.fromisoformat(str(prediction["kickoff"])).astimezone(UTC)
    captured = captured_at.astimezone(UTC)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "captured_at": captured.isoformat(),
        "fixture_id": fixture_id,
        "prediction_id": prediction.get("id"),
        "market": prediction.get("market"),
        "league": prediction.get("league"),
        "kickoff": kickoff.isoformat(),
        "seconds_to_kickoff": round(max(0.0, seconds_to_kickoff), 3),
        "time_to_kickoff_minutes": round(max(0.0, seconds_to_kickoff) / 60.0, 3),
        "bookmaker_id": quote.bookmaker_id,
        "bookmaker": quote.bookmaker_name,
        "odd": round(float(quote.odd), 4),
        "opposite_odd": round(float(quote.opposite_odd), 4),
        "market_overround": round(float(quote.overround), 6),
        "market_probability_devig": round(float(quote.devig_probability), 6),
        "model_probability": prediction.get("model_probability"),
        "calibrated_probability": prediction.get("calibrated_probability"),
        "decision_probability": round(decision_probability, 6),
        "expected_value": round(expected_value, 6),
        "probability_edge": round(probability_edge, 6),
        "signal_state": signal_state,
    }
    snapshot["observation_id"] = _observation_id(snapshot)
    return snapshot


def append_snapshots(
    root: Path, snapshots: list[dict[str, Any]], *, api_requests: int
) -> dict[str, int]:
    if not snapshots:
        return {"snapshots_appended": 0, "useful_observations": 0}

    path = root / SNAPSHOT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and row.get("observation_id"):
                        existing_ids.add(str(row["observation_id"]))
        except OSError:
            existing_ids = set()

    appended = 0
    useful = 0
    with path.open("a", encoding="utf-8") as handle:
        for snapshot in snapshots:
            observation_id = str(snapshot.get("observation_id") or _observation_id(snapshot))
            if observation_id in existing_ids:
                continue
            snapshot["observation_id"] = observation_id
            handle.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing_ids.add(observation_id)
            appended += 1
            if snapshot.get("signal_state") in {"NEAR_MISS", "STRONG", "SIGNAL_UPDATE"}:
                useful += 1
        handle.flush()

    metrics_path = root / METRICS_FILE
    metrics: dict[str, Any] = {}
    if metrics_path.exists():
        try:
            loaded = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metrics = loaded
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            metrics = {}
    metrics.update(
        {
            "schema_version": SCHEMA_VERSION,
            "updated_at": datetime.now(UTC).isoformat(),
            "last_run_api_requests": api_requests,
            "last_run_snapshots": appended,
            "last_run_useful_observations": useful,
            "total_snapshots": int(metrics.get("total_snapshots", 0)) + appended,
            "total_useful_observations": int(metrics.get("total_useful_observations", 0)) + useful,
        }
    )
    metrics["api_requests_per_useful_observation"] = round(
        api_requests / max(1, useful), 4
    )
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"snapshots_appended": appended, "useful_observations": useful}
