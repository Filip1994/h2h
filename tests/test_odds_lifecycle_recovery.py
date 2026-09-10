from datetime import UTC, datetime, timedelta

from quantbot.odds_lifecycle import lifecycle_contract


def test_lifecycle_recovers_latest_post_pick_pre_kickoff_observation():
    kickoff = datetime(2026, 9, 10, 2, 30, tzinfo=UTC)
    pick = kickoff - timedelta(hours=2)
    observations = [
        {"observation_id": "entry", "snapshot_type": "ENTRY", "odds_captured_at": pick.isoformat(), "odd": 3.45},
        {"observation_id": "mid", "snapshot_type": "INTERMEDIATE", "odds_captured_at": (kickoff - timedelta(minutes=18)).isoformat(), "odd": 3.30},
        {"observation_id": "late", "snapshot_type": "INTERMEDIATE", "odds_captured_at": (kickoff - timedelta(minutes=9)).isoformat(), "odd": 3.20},
    ]
    contract = lifecycle_contract(observations, pick_at=pick, kickoff=kickoff)
    assert contract["closing_available"] is True
    assert contract["closing"]["observation_id"] == "late"
    assert contract["closing_recovered"] is True
    assert contract["closing_snapshot_type"] == "INTERMEDIATE"
    assert contract["clv_status"] == "COMPUTABLE"


def test_lifecycle_does_not_use_entry_as_closing():
    kickoff = datetime(2026, 9, 10, 2, 30, tzinfo=UTC)
    pick = kickoff - timedelta(hours=2)
    observations = [
        {"observation_id": "entry", "snapshot_type": "ENTRY", "odds_captured_at": pick.isoformat(), "odd": 3.45},
    ]
    contract = lifecycle_contract(observations, pick_at=pick, kickoff=kickoff)
    assert contract["closing_available"] is False
    assert contract["closing_unavailable_reason"] == "NO_VALID_PRE_KICKOFF_CLOSE"
