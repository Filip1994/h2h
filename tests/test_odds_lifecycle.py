import json
from datetime import UTC, datetime, timedelta

from quantbot.odds_lifecycle import (
    canonical_observation,
    clv_from_odds,
    lifecycle_contract,
    select_closing,
    select_opening,
)


def observation(ts: datetime, odd: float, snapshot_type: str = "INTERMEDIATE") -> dict:
    return canonical_observation(
        fixture_id=1601522,
        market="OVER_2_5",
        bookmaker_id=8,
        bookmaker="Bet365",
        odd=odd,
        opposite_odd=1.8,
        captured_at=ts,
        snapshot_type=snapshot_type,
        prediction_id="p1",
    )


def test_opening_is_earliest_valid_pre_pick_observation():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    rows = [
        observation(base + timedelta(minutes=10), 1.9),
        observation(base + timedelta(minutes=30), 2.0),
        observation(base + timedelta(minutes=40), 2.1, "ENTRY"),
    ]
    selected = select_opening(rows, base + timedelta(minutes=45))
    assert selected["odd"] == 1.9


def test_entry_is_not_used_as_opening_when_no_intermediate_exists():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    rows = [observation(base + timedelta(minutes=40), 2.1, "ENTRY")]
    assert select_opening(rows, base + timedelta(minutes=45)) is None


def test_closing_is_only_t5_window_and_pre_kickoff():
    kickoff = datetime(2026, 9, 9, 12, tzinfo=UTC)
    rows = [
        observation(kickoff - timedelta(minutes=9), 1.9, "INTERMEDIATE"),
        observation(kickoff - timedelta(minutes=5), 2.0, "T5"),
        observation(kickoff + timedelta(minutes=1), 2.2, "CLOSING"),
    ]
    assert select_closing(rows, kickoff)["odd"] == 2.0


def test_clv_math_remains_existing_definition():
    assert clv_from_odds(2.0, 1.8) == 0.111111
    assert clv_from_odds(2.0, 2.0) == 0.0


def test_contract_exposes_missing_stages_without_fabrication():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    rows = [observation(base + timedelta(minutes=40), 2.1, "ENTRY")]
    contract = lifecycle_contract(
        rows,
        pick_at=base + timedelta(minutes=45),
        kickoff=base + timedelta(hours=2),
    )
    assert contract["opening"] is None
    assert contract["pick"] is None
    assert contract["closing"] is None
    assert contract["clv_status"] == "NOT_COMPUTABLE"


def test_canonical_observation_is_json_safe():
    row = observation(datetime(2026, 9, 9, 10, tzinfo=UTC), 2.0)
    json.dumps(row)
    assert row["schema_version"] == 1
