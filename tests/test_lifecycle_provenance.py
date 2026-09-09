from datetime import UTC, datetime, timedelta

from quantbot.odds_lifecycle import canonical_observation, lifecycle_contract


def test_observation_id_is_stable_and_contract_exposes_provenance() -> None:
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    opening = canonical_observation(
        fixture_id=1,
        market="OVER_2_5",
        bookmaker_id=8,
        bookmaker="Book",
        odd=2.0,
        opposite_odd=1.8,
        captured_at=base,
        snapshot_type="OPENING",
    )
    pick = canonical_observation(
        fixture_id=1,
        market="OVER_2_5",
        bookmaker_id=8,
        bookmaker="Book",
        odd=1.95,
        opposite_odd=1.85,
        captured_at=base + timedelta(minutes=30),
        snapshot_type="ENTRY",
    )
    closing = canonical_observation(
        fixture_id=1,
        market="OVER_2_5",
        bookmaker_id=8,
        bookmaker="Book",
        odd=1.9,
        opposite_odd=1.9,
        captured_at=base + timedelta(hours=1, minutes=55),
        snapshot_type="T5",
    )
    contract = lifecycle_contract(
        [opening, pick, closing],
        pick_at=base + timedelta(minutes=30),
        kickoff=base + timedelta(hours=2),
    )
    assert opening["observation_id"]
    assert opening["observation_id"] == canonical_observation(
        fixture_id=1,
        market="OVER_2_5",
        bookmaker_id=8,
        bookmaker="Book",
        odd=2.0,
        opposite_odd=1.8,
        captured_at=base,
        snapshot_type="OPENING",
    )["observation_id"]
    assert contract["opening_observation_id"] == opening["observation_id"]
    assert contract["pick_observation_id"] == pick["observation_id"]
    assert contract["closing_observation_id"] == closing["observation_id"]
    assert contract["opening_unavailable_reason"] is None


def test_missing_lifecycle_stage_has_explicit_reason() -> None:
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    contract = lifecycle_contract(
        [],
        pick_at=base,
        kickoff=base + timedelta(hours=2),
    )
    assert contract["opening_unavailable_reason"] == "NO_EARLIER_OBSERVATION"
    assert contract["pick_unavailable_reason"] == "NO_EXACT_ENTRY_OBSERVATION"
    assert contract["closing_unavailable_reason"] == "NO_VALID_PRE_KICKOFF_CLOSE"
