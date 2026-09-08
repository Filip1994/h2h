from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from quantbot.engine import QuantEngine

from test_engine_integration import FakeAPI


def test_h2h_telemetry_on_off_has_identical_decisions(settings) -> None:
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    off = replace(settings, h2h_telemetry_enabled=False)
    on = replace(settings, h2h_telemetry_enabled=True)

    off_engine = QuantEngine(off, api=FakeAPI(now))
    on_engine = QuantEngine(on, api=FakeAPI(now))
    off_result = off_engine.generate(now)
    on_result = on_engine.generate(now)

    assert [(b["market"], b["stake"], b["expected_value"], b["probability_edge"]) for b in off_result.new_bets] == [
        (b["market"], b["stake"], b["expected_value"], b["probability_edge"]) for b in on_result.new_bets
    ]
    off_predictions = {p["id"]: p for p in off_engine.prediction_store.load()}
    on_predictions = {p["id"]: p for p in on_engine.prediction_store.load()}
    for prediction_id in off_predictions:
        left = off_predictions[prediction_id]
        right = on_predictions[prediction_id]
        for key in ("model_probability", "calibrated_probability", "selected", "odd"):
            assert left[key] == right[key]


def test_one_fixture_three_markets_create_one_snapshot(settings) -> None:
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    research = replace(settings, h2h_telemetry_enabled=True)
    engine = QuantEngine(research, api=FakeAPI(now))
    engine.generate(now)
    snapshots = [
        line for line in (research.root / "data/h2h_snapshots.jsonl").read_text().splitlines() if line.strip()
    ]
    assert len(snapshots) == 1
    assert len(engine.prediction_store.load()) == 3
