from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.watchlist import _append_transition_event


def prediction() -> dict[str, object]:
    return {
        "id": "p1",
        "event_id": 42,
        "market": "UNDER_2_5",
        "kickoff": "2026-09-09T12:00:00+00:00",
    }


def quote() -> SimpleNamespace:
    return SimpleNamespace(
        bookmaker_id=8, bookmaker_name="Bet365", odd=1.9, opposite_odd=1.9
    )


def test_transition_history_is_only_written_on_class_change(tmp_path) -> None:
    captured = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
    args = {
        "root": tmp_path,
        "prediction": prediction(),
        "quote": quote(),
        "signal_class": "NEAR_MISS",
        "near_miss_reason": "EV_NEAR_THRESHOLD",
        "captured_at": captured,
        "expected_value": 0.08,
        "probability_edge": 0.04,
        "decision_probability": 0.57,
        "stake": 200.0,
        "seconds_to_kickoff": 7200,
    }
    _append_transition_event(**args, previous_class=None)
    _append_transition_event(**args, previous_class="NEAR_MISS")
    _append_transition_event(
        **{**args, "signal_class": "STRONG_SIGNAL", "near_miss_reason": None},
        previous_class="NEAR_MISS",
    )
    lines = (
        (tmp_path / "data" / "intraday_signal_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 2
    assert '"transition":"INITIAL->NEAR_MISS"' in lines[0]
    assert '"transition":"NEAR_MISS->STRONG_SIGNAL"' in lines[1]
