import json
from datetime import UTC, datetime, timedelta

from quantbot.odds_lifecycle import (
    canonical_observation,
    clv_from_odds,
    lifecycle_contract,
    observations_for,
    select_closing,
    select_first_seen,
    select_live,
    select_opening,
)


def observation(
    ts: datetime,
    odd: float,
    snapshot_type: str = "INTERMEDIATE",
    *,
    fixture_id: int = 1601522,
    market: str = "OVER_2_5",
    bookmaker_id: int = 8,
    selection: str | None = None,
) -> dict:
    return canonical_observation(
        fixture_id=fixture_id,
        market=market,
        bookmaker_id=bookmaker_id,
        bookmaker="Bet365",
        odd=odd,
        opposite_odd=1.8,
        captured_at=ts,
        snapshot_type=snapshot_type,
        selection=selection,
        prediction_id="p1",
    )


def test_first_seen_is_earliest_persisted_observation_independent_of_snapshot_type():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    rows = [
        observation(base + timedelta(minutes=10), 1.9, "CLOSING"),
        observation(base + timedelta(minutes=30), 2.0, "INTERMEDIATE"),
        observation(base + timedelta(minutes=40), 2.1, "ENTRY"),
    ]
    assert select_first_seen(rows)["odd"] == 1.9
    assert select_opening(rows, base + timedelta(minutes=45))["odd"] == 1.9


def test_observations_for_keeps_selection_isolated(tmp_path):
    path = tmp_path / "odds_snapshots.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(x)
            for x in (
                observation(datetime(2026, 9, 9, 10, tzinfo=UTC), 2.0, selection="OVER_2_5"),
                observation(datetime(2026, 9, 9, 10, tzinfo=UTC), 2.2, market="UNDER_2_5", selection="UNDER_2_5"),
            )
        )
        + "\n"
    )
    rows = observations_for(
        path,
        fixture_id=1601522,
        market="OVER_2_5",
        bookmaker_id=8,
        selection="OVER_2_5",
    )
    assert len(rows) == 1
    assert rows[0]["selection"] == "OVER_2_5"


def test_pick_requires_exact_entry_timestamp():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    rows = [
        observation(base + timedelta(minutes=40), 2.1, "ENTRY"),
        observation(base + timedelta(minutes=41), 2.2, "ENTRY"),
    ]
    contract = lifecycle_contract(
        rows,
        pick_at=base + timedelta(minutes=40),
        kickoff=base + timedelta(hours=2),
        build_at=base + timedelta(hours=1),
    )
    assert contract["pick"]["odd"] == 2.1
    assert contract["pick_observation_id"] == rows[0]["observation_id"]


def test_live_is_latest_persisted_at_build_and_never_after_kickoff():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    kickoff = base + timedelta(hours=2)
    rows = [
        observation(base + timedelta(minutes=40), 2.1, "ENTRY"),
        observation(base + timedelta(minutes=70), 2.0, "INTERMEDIATE"),
        observation(base + timedelta(minutes=90), 1.95, "INTERMEDIATE"),
        observation(kickoff + timedelta(minutes=1), 1.8, "CLOSING"),
    ]
    live = select_live(rows, build_at=base + timedelta(minutes=95), kickoff=kickoff)
    assert live["odd"] == 1.95
    assert datetime.fromisoformat(live["odds_captured_at"]).astimezone(UTC) < kickoff


def test_live_uses_build_time_cutoff():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    kickoff = base + timedelta(hours=2)
    rows = [
        observation(base + timedelta(minutes=70), 2.0, "INTERMEDIATE"),
        observation(base + timedelta(minutes=90), 1.95, "INTERMEDIATE"),
    ]
    live = select_live(rows, build_at=base + timedelta(minutes=80), kickoff=kickoff)
    assert live["odd"] == 2.0


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


def test_contract_exposes_four_stage_lifecycle_and_timeline():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    kickoff = base + timedelta(hours=2)
    rows = [
        observation(base + timedelta(minutes=10), 1.9, "OPENING"),
        observation(base + timedelta(minutes=40), 2.1, "ENTRY"),
        observation(base + timedelta(minutes=70), 2.0, "INTERMEDIATE"),
        observation(kickoff - timedelta(minutes=5), 1.95, "T5"),
    ]
    contract = lifecycle_contract(
        rows,
        pick_at=base + timedelta(minutes=40),
        kickoff=kickoff,
        build_at=kickoff - timedelta(minutes=4),
    )
    assert contract["first_seen"]["odd"] == 1.9
    assert contract["pick"]["odd"] == 2.1
    assert contract["live"]["odd"] == 1.95
    assert contract["closing"]["odd"] == 1.95
    assert contract["clv_status"] == "COMPUTABLE"
    assert [x["captured_at"] for x in contract["timeline"]] == sorted(
        x["captured_at"] for x in contract["timeline"]
    )
    assert {x["marker"] for x in contract["timeline"] if x["marker"]} == {
        "FIRST_SEEN",
        "PICK",
        "LIVE",
        "CLOSE",
    }


def test_contract_exposes_missing_stages_without_fabrication():
    base = datetime(2026, 9, 9, 10, tzinfo=UTC)
    rows = [observation(base + timedelta(minutes=40), 2.1, "INTERMEDIATE")]
    contract = lifecycle_contract(
        rows,
        pick_at=base + timedelta(minutes=45),
        kickoff=base + timedelta(hours=2),
        build_at=base + timedelta(hours=1),
    )
    assert contract["first_seen"]["odd"] == 2.1
    assert contract["pick"] is None
    assert contract["closing"] is None
    assert contract["clv_status"] == "NOT_COMPUTABLE"
    assert contract["pick_unavailable_reason"] == "NO_EXACT_ENTRY_OBSERVATION"


def test_canonical_observation_identity_includes_selection_but_not_time_or_lifecycle():
    at = datetime(2026, 9, 9, 10, tzinfo=UTC)
    later = at + timedelta(hours=3)
    first = observation(at, 2.0, "OPENING", selection="OVER_2_5")
    same_state_later = observation(later, 2.0, "CLOSING", selection="OVER_2_5")
    changed_price = observation(later, 2.1, "INTERMEDIATE", selection="OVER_2_5")
    under = observation(at, 2.0, market="UNDER_2_5", selection="UNDER_2_5")
    assert first["observation_id"] == same_state_later["observation_id"]
    assert first["observation_id"] != changed_price["observation_id"]
    assert first["observation_id"] != under["observation_id"]


def test_canonical_observation_is_json_safe_and_schema_is_v3():
    row = observation(datetime(2026, 9, 9, 10, tzinfo=UTC), 2.0)
    json.dumps(row)
    assert row["schema_version"] == 3
    assert row["observation_identity_version"] == 1
    assert row["selection"] == "OVER_2_5"
