from datetime import UTC, datetime

from quantbot.api import APIError
from quantbot.config import Settings
from quantbot.engine import QuantEngine
from quantbot.types import Market, MarketCandidate, OddsQuote

from test_engine_integration import FakeAPI


class ErrorH2HAPI(FakeAPI):
    def head_to_head(self, _home_id: int, _away_id: int) -> list[dict]:
        self.request_count += 1
        raise APIError("H2H rate limit")


def _settings(root, monkeypatch, enabled: bool):
    monkeypatch.setenv("H2H_TELEMETRY_ENABLED", "true" if enabled else "false")
    return Settings.from_env(root)


def test_market_candidate_telemetry_state_is_configuration_not_h2h_count() -> None:
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    quote = OddsQuote(Market.OVER_25, 2.0, 1.8, 8, "Test Book", now)
    base = dict(
        fixture_id=1,
        kickoff=now,
        league_id=10,
        league_name="Test League",
        country="Testland",
        home_id=1,
        home_name="Home",
        away_id=2,
        away_name="Away",
        market=Market.OVER_25,
        model_probability=0.55,
        calibrated_probability=0.54,
        decision_probability=0.54,
        h2h_rate=0.0,
        h2h_n=0,
        h2h_effective_n=0.0,
        h2h_history=(),
        quote=quote,
        lambda_home=1.2,
        lambda_away=1.0,
        rho=0.0,
        expected_value=0.08,
        probability_edge=0.04,
        calibration_status="UNCALIBRATED",
    )

    off = MarketCandidate(h2h_enabled=False, h2h_available=False, **base).to_bet(
        bet_id="1_OVER_2_5",
        stake=10,
        mode="PAPER",
        created_at=now,
        model_version="v2",
        xi=0.1,
    )
    on_no_history = MarketCandidate(
        h2h_enabled=True, h2h_available=False, **base
    ).to_bet(
        bet_id="1_OVER_2_5",
        stake=10,
        mode="PAPER",
        created_at=now,
        model_version="v2",
        xi=0.1,
    )
    assert off["h2h_enabled"] is False
    assert off["h2h_available"] is False
    assert on_no_history["h2h_enabled"] is True
    assert on_no_history["h2h_available"] is False
    assert on_no_history["h2h_n"] == 0


def test_engine_records_h2h_history_and_availability_when_enabled(settings, monkeypatch) -> None:
    monkeypatch.setenv("H2H_TELEMETRY_ENABLED", "true")
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    engine = QuantEngine(settings, api=FakeAPI(now))
    result = engine.generate(now)
    assert result.new_bets
    predictions = engine.prediction_store.load()
    assert predictions
    assert all(item["h2h_enabled"] is True for item in predictions)
    assert all(item["h2h_available"] is True for item in predictions)
    assert all(item["h2h_n"] == 5 for item in predictions)
    assert all(item["h2h_effective_n"] > 0 for item in predictions)
    assert all(item["h2h_history"] for item in predictions)
    bet = result.new_bets[0]
    assert bet["prediction_id"] == f"{bet['event_id']}_{bet['market']}_v2"
    assert bet["h2h_enabled"] is True
    assert bet["h2h_available"] is True
    assert bet["h2h_n"] == 5
    assert bet["h2h_history"]


def test_engine_records_h2h_api_error_as_unavailable(settings, monkeypatch) -> None:
    monkeypatch.setenv("H2H_TELEMETRY_ENABLED", "true")
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    engine = QuantEngine(settings, api=ErrorH2HAPI(now))
    result = engine.generate(now)
    assert result.new_bets
    predictions = engine.prediction_store.load()
    assert all(item["h2h_enabled"] is True for item in predictions)
    assert all(item["h2h_available"] is False for item in predictions)
    assert all(item["h2h_n"] == 0 for item in predictions)
    assert all(item["h2h_history"] == [] for item in predictions)


def test_h2h_on_off_does_not_change_betting_decision(tmp_path, monkeypatch) -> None:
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    off_root = tmp_path / "off"
    on_root = tmp_path / "on"
    off_root.mkdir()
    on_root.mkdir()

    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("PAPER_MODE", "true")
    monkeypatch.setenv("MIN_TRAINING_MATCHES", "20")
    monkeypatch.setenv("MIN_TEAM_MATCHES", "2")
    monkeypatch.setenv("MIN_CALIBRATION_SAMPLES", "10")
    monkeypatch.setenv("PROBABILITY_HAIRCUT", "0")
    monkeypatch.setenv("MIN_EDGE_PP", "0")
    monkeypatch.setenv("MIN_EV", "0")

    settings_off = _settings(off_root, monkeypatch, False)
    result_off = QuantEngine(settings_off, api=FakeAPI(now)).generate(now)
    settings_on = _settings(on_root, monkeypatch, True)
    result_on = QuantEngine(settings_on, api=FakeAPI(now)).generate(now)
    assert len(result_off.new_bets) == len(result_on.new_bets) == 1
    assert result_off.new_bets[0]["h2h_enabled"] is False
    assert result_off.new_bets[0]["h2h_available"] is False
    assert result_on.new_bets[0]["h2h_enabled"] is True
    assert result_on.new_bets[0]["h2h_available"] is True

    decision_fields = (
        "event_id",
        "market",
        "odd",
        "opposite_odd",
        "model_probability",
        "calibrated_probability",
        "decision_probability",
        "probability_edge",
        "expected_value",
        "stake",
        "lambda_home",
        "lambda_away",
        "rho",
    )
    for field in decision_fields:
        assert result_off.new_bets[0][field] == result_on.new_bets[0][field]


def test_near_miss_event_preserves_h2h_telemetry(settings) -> None:
    from quantbot.watchlist import _event_from_prediction

    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    quote = OddsQuote(Market.OVER_25, 2.0, 1.8, 8, "Test Book", now)
    prediction = {
        "id": "999_OVER_2_5_v2",
        "event_id": 999,
        "market": "OVER_2_5",
        "h2h_enabled": True,
        "h2h_available": True,
        "h2h_rate": 0.6,
        "h2h_n": 5,
        "h2h_effective_n": 4.2,
        "h2h_history": ["2-1", "1-0"],
    }
    event = _event_from_prediction(
        prediction,
        quote=quote,
        decision_probability=0.55,
        expected_value=0.1,
        probability_edge=0.05,
        stake=5,
        now=now,
        linked_bet=None,
        signal_type="NEW_OPPORTUNITY",
    )
    assert event["signal_id"] == event["id"]
    assert event["prediction_id"] == prediction["id"]
    assert event["h2h_enabled"] is True
    assert event["h2h_available"] is True
    assert event["h2h_n"] == 5
    assert event["h2h_history"] == ["2-1", "1-0"]
