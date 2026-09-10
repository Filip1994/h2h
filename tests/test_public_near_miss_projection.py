# fmt: off
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.build_public_signal_buckets import build


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def prediction(now: datetime, *, status="PENDING") -> dict:
    return {
        "id": "501_UNDER_2_5_dc-value-v2.1.0",
        "event_id": 501,
        "market": "UNDER_2_5",
        "selection": "UNDER_2_5",
        "home_name": "Alpha FC",
        "away_name": "Beta FC",
        "match": "Alpha FC vs Beta FC",
        "league": "Test League",
        "kickoff": (now + timedelta(hours=2)).isoformat(),
        "status": status,
    }


def observation(pred: dict, captured: datetime, odd: float) -> dict:
    return {
        "fixture_id": pred["event_id"], "prediction_id": pred["id"],
        "market": pred["market"], "selection": pred["selection"],
        "market_display": "Under 2.5", "league": pred["league"],
        "kickoff": pred["kickoff"], "bookmaker_id": 8, "bookmaker": "Bet365",
        "odd": odd, "opposite_odd": 2.10, "captured_at": captured.isoformat(),
        "observation_id": f"obs-{captured.timestamp()}",
        "signal_class": "NEAR_MISS", "signal_state": "NEAR_MISS",
        "near_miss_reason": "EDGE_NEAR_THRESHOLD", "model_probability": 0.62,
        "calibrated_probability": 0.62, "decision_probability": 0.60,
        "probability_edge": 0.04, "expected_value": 0.03,
    }


def setup(tmp_path, pred, observations, alerts=None):
    write_json(tmp_path / "predictions.json", [pred])
    write_json(tmp_path / "bets.json", [])
    write_json(tmp_path / "intraday_alerts.json", alerts or [])
    write_json(tmp_path / "near_misses.json", [])
    write_jsonl(tmp_path / "data" / "market_timing_snapshots.jsonl", observations)
    write_jsonl(tmp_path / "data" / "odds_snapshots.jsonl", [])
    write_jsonl(tmp_path / "data" / "intraday_signal_events.jsonl", [])


def test_public_projection_preserves_identity_and_lifecycle(tmp_path):
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    pred = prediction(now)
    setup(tmp_path, pred, [observation(pred, now - timedelta(minutes=30), 1.55), observation(pred, now - timedelta(minutes=5), 1.60)])
    _, near = build(tmp_path)
    row = near[0]
    assert row["home_name"] == "Alpha FC" and row["away_name"] == "Beta FC"
    assert row["match"] == "Alpha FC vs Beta FC" and row["league"] == "Test League"
    assert row["bookmaker_id"] == 8 and row["status"] == "PENDING"
    assert row["opening_odd"] is None and row["closing_odd"] is None
    assert row["not_a_production_bet"] is True


def test_public_projection_uses_terminal_prediction_lifecycle(tmp_path):
    now = datetime(2026, 9, 10, 14, tzinfo=UTC)
    pred = prediction(now, status="SETTLED")
    pred.update({"outcome": 1, "result": "2:0", "settled_at": now.isoformat()})
    setup(tmp_path, pred, [observation(pred, now - timedelta(hours=2), 1.60)])
    _, near = build(tmp_path)
    row = near[0]
    assert row["status"] == "WIN"
    assert row["result"] == "2:0" and row["settled_at"] == now.isoformat()
    assert row["settlement_type"] == "OBSERVATIONAL_VIRTUAL"
    assert row["virtual_settled"] is True and row["profit"] == 0.0


def test_public_projection_keeps_exact_promotion_and_does_not_fabricate_closing(tmp_path):
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    pred = prediction(now)
    near = observation(pred, now - timedelta(minutes=10), 1.60)
    alert = {
        "id": "signal-501", "signal_id": "signal-501", "prediction_id": pred["id"],
        "event_id": 501, "fixture_id": 501, "market": "UNDER_2_5", "selection": "UNDER_2_5",
        "bookmaker_id": 8, "bookmaker": "Bet365", "signal_class": "STRONG_SIGNAL",
        "odd": 1.70, "signal_sent_at": (now - timedelta(minutes=5)).isoformat(), "status": "PENDING",
    }
    setup(tmp_path, pred, [near], [alert])
    _, near_rows = build(tmp_path)
    row = near_rows[0]
    assert row["status"] == "PROMOTED"
    assert row["promoted_to_signal_id"] == "signal-501"
    assert row["pick_odd"] == 1.70 and row["closing_odd"] is None
    assert row["not_a_production_bet"] is True
# fmt: on
