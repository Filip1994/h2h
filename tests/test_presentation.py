from quantbot.presentation import (
    clv_interpretation,
    clv_label,
    market_display,
    odds_lifecycle,
    status_display,
)


def test_market_display_is_canonical() -> None:
    assert market_display("UNDER_2_5") == "Under 2.5"
    assert market_display("Less than 2.5") == "Under 2.5"
    assert market_display("Ukupno Golova - Manje 2.5") == "Under 2.5"
    assert market_display("BTTS_YES") == "BTTS — Yes"
    assert market_display("BTTS_NO") == "BTTS — No"


def test_status_display_maps_loss_and_skip_without_collapsing_them() -> None:
    assert status_display("PENDING") == "PENDING"
    assert status_display("WIN") == "WON"
    assert status_display("LOSS") == "LOST"
    assert status_display("SKIPPED") == "SKIPPED"


def test_clv_display_preserves_canonical_decimal_math() -> None:
    assert clv_label(0.133333) == "+13.33%"
    assert clv_label(-0.0421) == "−4.21%"
    assert clv_label(0.0) == "0.00%"
    assert clv_interpretation(0.01) == "Beat close"
    assert clv_interpretation(-0.01) == "Lost to close"
    assert clv_interpretation(0.0) == "Even"
    assert clv_label(None) == "—"


def test_odds_lifecycle_does_not_infer_missing_values() -> None:
    life = odds_lifecycle({"odd": 1.95})
    assert life["opening"] is None
    assert life["pick"] == 1.95
    assert life["closing"] is None


def test_odds_lifecycle_exposes_opening_pick_and_closing() -> None:
    life = odds_lifecycle(
        {
            "opening_odd": 2.0,
            "odd": 1.95,
            "closing_odd": 1.88,
            "opening_odds_captured_at": "2026-09-08T08:00:00+00:00",
            "odds_captured_at": "2026-09-08T10:00:00+00:00",
            "closing_odds_captured_at": "2026-09-08T12:00:00+00:00",
        }
    )
    assert life == {
        "opening": 2.0,
        "pick": 1.95,
        "closing": 1.88,
        "opening_at": "2026-09-08T08:00:00+00:00",
        "pick_at": "2026-09-08T10:00:00+00:00",
        "closing_at": "2026-09-08T12:00:00+00:00",
    }
