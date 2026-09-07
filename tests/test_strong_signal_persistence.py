from __future__ import annotations

import json
from datetime import UTC, datetime

from main import persist_intraday_strong_signals


def test_generate_strong_signal_is_persisted_and_deduplicated(settings) -> None:
    now = datetime(2026, 9, 7, 16, 30, tzinfo=UTC)
    bet = {
        "id": "bet-strong-001",
        "prediction_id": "pred-001",
        "event_id": 123,
        "market": "OVER_2_5",
        "market_display": "Over 2.5",
        "match": "Test FC vs Example FC",
        "league": "Test League",
        "kickoff": "2026-09-07T18:00:00+00:00",
        "odd": 1.90,
        "opposite_odd": 1.80,
        "bookmaker_id": 8,
        "bookmaker": "Bet365",
        "odds_captured_at": now.isoformat(),
        "model_probability": 0.70,
        "calibrated_probability": 0.70,
        "decision_probability": 0.70,
        "probability_edge": 0.10,
        "expected_value": 0.33,
        "stake": 500.0,
        "status": "PENDING",
        "profit": 0.0,
    }

    persist_intraday_strong_signals(settings, (bet,), now)
    persist_intraday_strong_signals(settings, (bet,), now)

    alerts_path = settings.root / "intraday_alerts.json"
    alerts = json.loads(alerts_path.read_text(encoding="utf-8"))

    assert len(alerts) == 1
    assert alerts[0]["id"] == "generate:bet-strong-001"
    assert alerts[0]["linked_bet_id"] == "bet-strong-001"
    assert alerts[0]["signal_source"] == "INTRADAY_ALERT"
    assert alerts[0]["persistence_source"] == "GENERATE"
    assert alerts[0]["signal_sent_at"] == now.isoformat()
