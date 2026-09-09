from datetime import UTC, datetime
from pathlib import Path
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
        quote=OddsQuote(Market.OVER_25, 2.1, 1.7, 99, "TestBook", datetime(2026, 9, 10, 12, tzinfo=UTC)),
    )
    model = SimpleNamespace(fitted_matches=120, team_ids=(10, 20, 30))
    packet = build_packet(candidate, 250.0, settings=settings, model=model, decision_timestamp=datetime(2026, 9, 10, 12, tzinfo=UTC))
    assert verify_packet(packet)
    packet["decision"]["pick_odd"] = 2.2
    assert not verify_packet(packet)
