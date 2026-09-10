from datetime import UTC, datetime

from quantbot.market_timing import build_snapshot


class Quote:
    bookmaker_id = 8
    bookmaker_name = "Bet365"
    odd = 1.70
    opposite_odd = 2.10
    overround = 1 / odd + 1 / opposite_odd - 1
    devig_probability = (1 / odd) / ((1 / odd) + (1 / opposite_odd))


def test_market_timing_snapshot_persists_fixture_identity():
    snapshot = build_snapshot(
        fixture_id=501,
        prediction={
            "id": "501_UNDER_2_5_dc-value-v2.1.0",
            "market": "UNDER_2_5",
            "league": "Test League",
            "kickoff": "2026-09-10T14:00:00+00:00",
            "home_name": "Alpha FC",
            "away_name": "Beta FC",
        },
        quote=Quote(),
        decision_probability=0.60,
        expected_value=0.03,
        probability_edge=0.04,
        seconds_to_kickoff=7200,
        signal_state="NEAR_MISS",
        captured_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
    )

    assert snapshot["home_name"] == "Alpha FC"
    assert snapshot["away_name"] == "Beta FC"
    assert snapshot["match"] == "Alpha FC vs Beta FC"
