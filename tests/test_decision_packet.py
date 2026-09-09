from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.decision_packet import build_packet, verify_packet
from quantbot.types import Market, OddsQuote


def test_decision_packet_is_self_verifying(settings) -> None:
    candidate = SimpleNamespace(
        fixture_id=123,
        league_id=1,
        league_name="Test League",
        country="Test",
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
        quote=OddsQuote(Market.OVER_25, 2.1, 1.7, 99, "TestBook", datetime(2026, 9, 10, 12, tzinfo=UTC)),
    )
    packet = build_packet(candidate, 250.0, settings=settings, decision_timestamp=datetime(2026, 9, 10, 12, tzinfo=UTC), calibration_hash="cal-hash")
    assert verify_packet(packet)
    assert packet["decision"]["pick_observation_id"]
    assert packet["model"]["training_sample"]["identity"] == "train-hash"
    packet["decision"]["pick_odd"] = 2.2
    assert not verify_packet(packet)
