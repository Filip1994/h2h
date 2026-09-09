import json
from datetime import UTC, datetime, timedelta

from quantbot.odds_lifecycle import canonical_observation
from tools.enrich_public_strong_signal_lifecycle import enrich_row


def test_strong_signal_lifecycle_uses_canonical_observations_without_fabrication():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    observations = [
        canonical_observation(
            fixture_id=1,
            market="OVER_2_5",
            bookmaker_id=8,
            bookmaker="Bet365",
            odd=1.80,
            opposite_odd=2.00,
            captured_at=base,
            snapshot_type="OPENING",
            prediction_id="p1",
        ),
        canonical_observation(
            fixture_id=1,
            market="OVER_2_5",
            bookmaker_id=8,
            bookmaker="Bet365",
            odd=2.00,
            opposite_odd=1.80,
            captured_at=base + timedelta(minutes=30),
            snapshot_type="ENTRY",
            prediction_id="p1",
        ),
        canonical_observation(
            fixture_id=1,
            market="OVER_2_5",
            bookmaker_id=8,
            bookmaker="Bet365",
            odd=1.90,
            opposite_odd=1.90,
            captured_at=base + timedelta(minutes=55),
            snapshot_type="T5",
            prediction_id="p1",
        ),
    ]
    row = {
        "id": "s1",
        "event_id": 1,
        "market": "OVER_2_5",
        "bookmaker_id": 8,
        "bookmaker": "Bet365",
        "odd": 2.00,
        "odds_captured_at": (base + timedelta(minutes=30)).isoformat(),
        "kickoff": (base + timedelta(hours=1)).isoformat(),
        "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL",
        "not_a_production_bet": True,
        "virtual_profit": 0.0,
        "profit": 0.0,
    }
    coverage = enrich_row(row, {(1, "OVER_2_5", 8): observations})

    assert coverage == "FULLY_AUDITABLE"
    assert row["opening_odd"] == 1.8
    assert row["odd"] == 2.0
    assert row["closing_odd"] == 1.9
    assert row["clv_odds_pct"] == round(2.0 / 1.9 - 1, 6)
    assert row["clv_status"] == "COMPUTABLE"
    assert row["virtual_profit"] == 0.0
    assert row["profit"] == 0.0
    json.dumps(row)


def test_strong_signal_lifecycle_keeps_missing_close_unavailable():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    opening = canonical_observation(
        fixture_id=2,
        market="UNDER_2_5",
        bookmaker_id=11,
        bookmaker="1xBet",
        odd=2.10,
        opposite_odd=1.70,
        captured_at=base,
        snapshot_type="INTERMEDIATE",
        prediction_id="p2",
    )
    entry = canonical_observation(
        fixture_id=2,
        market="UNDER_2_5",
        bookmaker_id=11,
        bookmaker="1xBet",
        odd=2.20,
        opposite_odd=1.65,
        captured_at=base + timedelta(minutes=20),
        snapshot_type="ENTRY",
        prediction_id="p2",
    )
    row = {
        "id": "s2",
        "event_id": 2,
        "market": "UNDER_2_5",
        "bookmaker_id": 11,
        "odd": 2.20,
        "odds_captured_at": (base + timedelta(minutes=20)).isoformat(),
        "kickoff": (base + timedelta(hours=1)).isoformat(),
    }
    coverage = enrich_row(row, {(2, "UNDER_2_5", 11): [opening, entry]})

    assert coverage == "PARTIAL"
    assert row["opening_odd"] == 2.1
    assert row["closing_odd"] is None
    assert row["clv_odds_pct"] is None
    assert row["clv_status"] == "NOT_COMPUTABLE"
