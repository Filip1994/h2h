from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.decision_packet import build_packet, registry_snapshot, verify_packet
from quantbot.observation_identity import canonical_observation_id
from quantbot.types import Market, OddsQuote


def test_decision_packet_is_self_verifying_and_registry_pinned(settings) -> None:
    candidate = SimpleNamespace(
        fixture_id=123,
        league_id=39,
        league_name="Premier League",
        country="England",
        home_id=10,
        home_name="Home",
        away_id=20,
        away_name="Away",
        kickoff=datetime(2026, 9, 10, 18, tzinfo=UTC),
        market=Market.OVER_25,
        model_probability=0.55,
        calibrated_probability=0.54,
        decision_probability=0.51,
        expected_value=0.08,
        probability_edge=0.05,
        calibration_status="VALIDATED",
        model_version="dc-value-v2.1.0",
        model_fitted_matches=120,
        model_team_count=30,
        model_training_cutoff="2026-09-10T10:00:00+00:00",
        model_training_identity="train-hash",
        quote=OddsQuote(
            Market.OVER_25,
            2.1,
            1.7,
            99,
            "TestBook",
            datetime(2026, 9, 10, 12, tzinfo=UTC),
        ),
    )
    packet = build_packet(
        candidate,
        250.0,
        settings=settings,
        decision_timestamp=datetime(2026, 9, 10, 12, tzinfo=UTC),
        calibration_hash="cal-hash",
    )
    assert verify_packet(packet)
    assert packet["schema_version"] == 3
    assert packet["decision"]["pick_observation_id"] == canonical_observation_id(
        fixture_id=123,
        market="OVER_2_5",
        bookmaker_id=99,
        selection="OVER_2_5",
        odd=2.1,
        opposite_odd=1.7,
    )
    assert packet["provenance"]["observation_identity"]["version"] == 1
    assert packet["model"]["training_sample"]["identity"] == "train-hash"
    assert packet["strategy"]["registry_version"] == registry_snapshot(39)["version"]
    assert packet["strategy"]["registry_league_id"] == 39
    assert packet["strategy"]["registry_classification"]["tier"] == 1

    packet["decision"]["pick_odd"] = 2.2
    assert not verify_packet(packet)


def test_registry_snapshot_is_deterministic(settings) -> None:
    first = registry_snapshot(39)
    second = registry_snapshot(39)
    assert first == second
    assert first["version"]
    assert first["classification"]["league_name"] == "Premier League"
