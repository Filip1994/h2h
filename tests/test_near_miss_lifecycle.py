# fmt: off
import json  # noqa: I001
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.build_near_miss_lifecycle import build


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def base_prediction(now: datetime) -> dict:
    return {"id": "101_UNDER_2_5_dc-value-v2.1.0", "event_id": 101, "market": "UNDER_2_5", "home_name": "Alpha FC", "away_name": "Beta FC", "match": "Alpha FC vs Beta FC", "league": "Test League", "kickoff": (now + timedelta(hours=1)).isoformat()}


def snapshot(prediction: dict, captured: datetime, odd: float, near=True) -> dict:
    return {"fixture_id": prediction["event_id"], "prediction_id": prediction["id"], "market": prediction["market"], "market_display": "Under 2.5", "league": prediction["league"], "kickoff": prediction["kickoff"], "bookmaker_id": 8, "bookmaker": "Bet365", "odd": odd, "opposite_odd": 2.0, "captured_at": captured.isoformat(), "observation_id": f"obs-{captured.timestamp()}", "signal_class": "NEAR_MISS" if near else "OBSERVED", "signal_state": "NEAR_MISS" if near else "OBSERVED", "near_miss_reason": "EDGE_NEAR_THRESHOLD" if near else None, "model_probability": 0.62, "calibrated_probability": 0.62, "decision_probability": 0.60, "probability_edge": 0.04, "expected_value": 0.03}


def canonical(snapshot_row: dict, captured: datetime, snapshot_type: str) -> dict:
    return {"fixture_id": snapshot_row["fixture_id"], "market": snapshot_row["market"], "bookmaker_id": snapshot_row["bookmaker_id"], "bookmaker": snapshot_row["bookmaker"], "odd": snapshot_row["odd"], "opposite_odd": snapshot_row["opposite_odd"], "odds_captured_at": captured.isoformat(), "snapshot_type": snapshot_type, "observation_id": f"canon-{captured.timestamp()}"}


def test_identity_lifecycle_and_exact_bookmaker(tmp_path):
    now = datetime(2026, 9, 10, 12, tzinfo=UTC); prediction = base_prediction(now); first = snapshot(prediction, now - timedelta(minutes=30), 1.55); near = snapshot(prediction, now - timedelta(minutes=10), 1.58)
    write_json(tmp_path / "predictions.json", [prediction]); write_json(tmp_path / "bets.json", []); write_json(tmp_path / "intraday_alerts.json", []); write_json(tmp_path / "near_misses.json", []); write_jsonl(tmp_path / "data" / "market_timing_snapshots.jsonl", [first, near]); write_jsonl(tmp_path / "data" / "odds_snapshots.jsonl", [canonical(first, now - timedelta(minutes=40), "INTERMEDIATE"), canonical(first, now - timedelta(minutes=5), "T5")])
    row = build(tmp_path, now=now)[0]
    assert row["home_name"] == "Alpha FC"; assert row["away_name"] == "Beta FC"; assert row["match"] == "Alpha FC vs Beta FC"; assert row["bookmaker_id"] == 8; assert row["opening_odd"] == 1.55; assert row["closing_odd"] == 1.55; assert row["status"] == "PENDING"; assert row["not_a_production_bet"] is True


def test_promoted_near_miss_is_linked_without_becoming_production(tmp_path):
    now = datetime(2026, 9, 10, 12, tzinfo=UTC); prediction = base_prediction(now); near = snapshot(prediction, now - timedelta(minutes=10), 1.60)
    write_json(tmp_path / "predictions.json", [prediction]); write_json(tmp_path / "bets.json", []); write_json(tmp_path / "near_misses.json", []); write_json(tmp_path / "intraday_alerts.json", [{"id": "signal-101", "signal_id": "signal-101", "prediction_id": prediction["id"], "event_id": 101, "market": "UNDER_2_5", "bookmaker_id": 8, "bookmaker": "Bet365", "signal_class": "STRONG_SIGNAL", "odd": 1.70, "signal_sent_at": (now - timedelta(minutes=5)).isoformat()}]); write_jsonl(tmp_path / "data" / "market_timing_snapshots.jsonl", [near]); write_jsonl(tmp_path / "data" / "odds_snapshots.jsonl", [])
    row = build(tmp_path, now=now)[0]
    assert row["status"] == "PROMOTED"; assert row["promoted_to_signal_id"] == "signal-101"; assert row["not_a_production_bet"] is True


def test_other_bookmaker_cannot_promote_exact_near_miss(tmp_path):
    now = datetime(2026, 9, 10, 12, tzinfo=UTC); prediction = base_prediction(now); near = snapshot(prediction, now - timedelta(minutes=10), 1.60)
    write_json(tmp_path / "predictions.json", [prediction]); write_json(tmp_path / "bets.json", []); write_json(tmp_path / "near_misses.json", []); write_json(tmp_path / "intraday_alerts.json", [{"id": "signal-wrong-book", "signal_id": "signal-wrong-book", "prediction_id": prediction["id"], "event_id": 101, "market": "UNDER_2_5", "bookmaker_id": 11, "bookmaker": "1xBet", "signal_class": "STRONG_SIGNAL", "odd": 1.80, "signal_sent_at": (now - timedelta(minutes=5)).isoformat()}]); write_jsonl(tmp_path / "data" / "market_timing_snapshots.jsonl", [near]); write_jsonl(tmp_path / "data" / "odds_snapshots.jsonl", [])
    row = build(tmp_path, now=now)[0]
    assert row["status"] == "PENDING"; assert row["promoted_to_signal_id"] is None; assert row["bookmaker_id"] == 8


def test_non_promoted_near_miss_expires_after_kickoff(tmp_path):
    now = datetime(2026, 9, 10, 14, tzinfo=UTC); prediction = base_prediction(datetime(2026, 9, 10, 12, tzinfo=UTC)); near = snapshot(prediction, datetime(2026, 9, 10, 12, 30, tzinfo=UTC), 1.58)
    write_json(tmp_path / "predictions.json", [prediction]); write_json(tmp_path / "bets.json", []); write_json(tmp_path / "intraday_alerts.json", []); write_json(tmp_path / "near_misses.json", []); write_jsonl(tmp_path / "data" / "market_timing_snapshots.jsonl", [near]); write_jsonl(tmp_path / "data" / "odds_snapshots.jsonl", [])
    row = build(tmp_path, now=now)[0]
    assert row["status"] == "EXPIRED"; assert row["settled_at"] is None; assert row["profit"] == 0.0
# fmt: on
