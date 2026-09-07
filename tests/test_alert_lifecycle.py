from __future__ import annotations

from datetime import UTC, datetime

from quantbot.alert_lifecycle import (
    _apply_closing,
    _clv_pct,
    _settle_counterfactual,
)


class Quote:
    odd = 1.72
    opposite_odd = 2.10
    devig_probability = 0.565


def test_entry_quote_is_immutable_and_t5_is_separate_snapshot():
    alert = {
        "odd": 1.88,
        "opposite_odd": 2.01,
        "closing_5m_odd": None,
    }
    _apply_closing(alert, Quote(), datetime(2026, 9, 7, 19, 10, tzinfo=UTC))
    assert alert["odd"] == 1.88
    assert alert["opposite_odd"] == 2.01
    assert alert["closing_5m_odd"] == 1.72
    assert alert["closing_5m_opposite_odd"] == 2.10


def test_clv_uses_entry_vs_t5_not_latest_quote():
    assert _clv_pct(1.88, 1.72) == round(1.88 / 1.72 - 1.0, 6)


def test_counterfactual_alert_settles_and_keeps_entry_odd():
    alert = {
        "market": "OVER_2_5",
        "stake": 500.0,
        "odd": 1.88,
        "closing_5m_odd": 1.72,
        "status": "PENDING",
    }
    changed = _settle_counterfactual(
        alert,
        "FT",
        (3, 1),
        datetime(2026, 9, 7, 21, 0, tzinfo=UTC),
    )
    assert changed
    assert alert["status"] == "WIN"
    assert alert["profit"] == 440.0
    assert alert["odd"] == 1.88
    assert alert["settlement_type"] == "COUNTERFACTUAL_ALERT"
    assert alert["clv_odds_pct"] == round(1.88 / 1.72 - 1.0, 6)
