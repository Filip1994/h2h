import json
from datetime import UTC, datetime, timedelta

from quantbot.calibration import ProbabilityCalibrator, refit_calibration
from quantbot.monitor import LedgerMonitor, market_outcome, regulation_score, skip_bet
from quantbot.storage import BetStore, PredictionStore
from quantbot.types import Market


def test_market_aliases_settle_identically() -> None:
    assert Market.parse("Više 2.5 Golova") == Market.OVER_25
    assert market_outcome(Market.OVER_25, 2, 1)
    assert not market_outcome(Market.UNDER_25, 2, 1)
    assert market_outcome(Market.BTTS_YES, 1, 1)


def test_aet_uses_regulation_fulltime_score() -> None:
    payload = {
        "fixture": {"status": {"short": "AET"}},
        "goals": {"home": 3, "away": 2},
        "score": {
            "fulltime": {"home": 1, "away": 1},
            "extratime": {"home": 3, "away": 2},
        },
    }
    assert regulation_score(payload) == (1, 1)


def test_skip_is_exact_not_substring(settings) -> None:
    store = BetStore(settings.bets_file)
    store.save(
        [
            {"id": "12_OVER_2_5", "event_id": 12, "status": "PENDING"},
            {"id": "120_OVER_2_5", "event_id": 120, "status": "PENDING"},
        ]
    )
    assert skip_bet(store, "SKIP_12_OVER_2_5", datetime.now(UTC))
    bets = store.load()
    assert bets[0]["status"] == "SKIPPED"
    assert bets[1]["status"] == "PENDING"


def test_calibration_requires_and_validates_oos_sample(settings) -> None:
    predictions = []
    start = datetime(2025, 1, 1, tzinfo=UTC)
    for index in range(300):
        predictions.append(
            {
                "market": Market.OVER_25.value,
                "status": "SETTLED",
                "outcome": index % 2,
                "model_probability": 0.80,
                "kickoff": (start + timedelta(days=index)).isoformat(),
            }
        )
    settings.predictions_file.write_text(json.dumps(predictions), encoding="utf-8")
    result = refit_calibration(
        settings.predictions_file, settings.calibration_file, min_samples=10
    )
    assert result[Market.OVER_25.value]["validated"] is True
    calibrator = ProbabilityCalibrator.load(settings.calibration_file, min_samples=10)
    calibrated, status = calibrator.apply(Market.OVER_25, 0.80)
    assert status.startswith("PLATT_N_")
    assert 0.45 < calibrated < 0.55


def test_calibration_preserves_valid_import_until_online_sample_is_large(
    settings,
) -> None:
    prior = {
        Market.OVER_25.value: {
            "a": 0.8,
            "b": -0.1,
            "n": 300,
            "validated": True,
            "method": "PLATT",
        }
    }
    settings.calibration_file.write_text(json.dumps(prior), encoding="utf-8")
    settings.predictions_file.write_text("[]", encoding="utf-8")
    result = refit_calibration(
        settings.predictions_file,
        settings.calibration_file,
        min_samples=200,
        preserve_existing=True,
    )
    retained = result[Market.OVER_25.value]
    assert retained["a"] == 0.8
    assert retained["n"] == 300
    assert retained["validated"] is True
    assert retained["retained_pending_new_sample"] == 0


class FinishedFixtureAPI:
    request_count = 0

    def fixture(self, _fixture_id: int) -> list[dict]:
        self.request_count += 1
        return [
            {
                "fixture": {"status": {"short": "FT"}},
                "goals": {"home": 2, "away": 1},
                "score": {"fulltime": {"home": 2, "away": 1}},
            }
        ]

    def odds(self, _fixture_id: int) -> list[dict]:
        self.request_count += 1
        return []


def test_monitor_settles_bet_and_prediction(settings) -> None:
    now = datetime(2026, 9, 4, 18, 0, tzinfo=UTC)
    bet_store = BetStore(settings.bets_file)
    prediction_store = PredictionStore(settings.predictions_file)
    bet_store.save(
        [
            {
                "id": "77_OVER_2_5",
                "event_id": 77,
                "kickoff": (now - timedelta(hours=3)).isoformat(),
                "market": "Više 2.5 Golova",
                "status": "PENDING",
                "stake": 500,
                "odd": 1.80,
            }
        ]
    )
    prediction_store.save(
        [
            {
                "id": "prediction",
                "event_id": 77,
                "kickoff": (now - timedelta(hours=3)).isoformat(),
                "market": Market.OVER_25.value,
                "status": "PENDING",
            }
        ]
    )
    result = LedgerMonitor(
        settings,
        api=FinishedFixtureAPI(),
        bet_store=bet_store,
        prediction_store=prediction_store,
    ).run(now)
    settled = bet_store.load()[0]
    assert result["settled_bets"] == 1
    assert settled["status"] == "WIN"
    assert settled["profit"] == 400
    assert prediction_store.load()[0]["outcome"] == 1
