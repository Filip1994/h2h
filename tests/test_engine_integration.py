from datetime import UTC, datetime, timedelta

import pytest

from quantbot.config import Settings
from quantbot.engine import QuantEngine


def api_fixture(fixture_id: int, date: datetime, home_id: int, away_id: int, home_goals: int | None, away_goals: int | None, *, status: str, season: int = 2026) -> dict:
    return {"fixture": {"id": fixture_id, "date": date.isoformat(), "status": {"short": status}}, "league": {"id": 39, "name": "Premier League", "country": "England", "season": season}, "teams": {"home": {"id": home_id, "name": f"Team {home_id}"}, "away": {"id": away_id, "name": f"Team {away_id}"}}, "goals": {"home": home_goals, "away": away_goals}, "score": {"halftime": {"home": 1 if home_goals is not None and home_goals > 0 else 0, "away": 0}, "fulltime": {"home": home_goals, "away": away_goals}}}


class FakeAPI:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.request_count = 0

    def usage_snapshot(self) -> dict:
        return {"request_count": self.request_count}

    def fixtures_by_date(self, _date: str) -> list[dict]:
        self.request_count += 1
        return [api_fixture(999, self.now + timedelta(hours=4), 1, 2, None, None, status="NS")]

    def league_season_fixtures(self, _league_id: int, season: int) -> list[dict]:
        self.request_count += 1
        matches: list[dict] = []
        fixture_id = season * 10_000
        date = datetime(season, 1, 1, tzinfo=UTC)
        index = 0
        for home_id in range(1, 7):
            for away_id in range(1, 7):
                if home_id == away_id:
                    continue
                matches.append(api_fixture(fixture_id + index, date + timedelta(days=index), home_id, away_id, (home_id + away_id + index) % 4, (away_id + index) % 3, status="FT", season=season))
                index += 1
        return matches

    def odds(self, _fixture_id: int) -> list[dict]:
        self.request_count += 1
        return [{"bookmakers": [{"id": 8, "name": "Test Book", "bets": [{"name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "3.00"}, {"value": "Under 2.5", "odd": "1.20"}]}, {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "3.00"}, {"value": "No", "odd": "1.20"}]}]}]}]


def test_engine_persists_all_qualifying_markets_and_blocks_fixture_on_rerun(settings) -> None:
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    engine = QuantEngine(settings, api=FakeAPI(now))
    first = engine.generate(now)
    assert len(first.new_bets) == 2
    assert {bet["event_id"] for bet in first.new_bets} == {999}
    assert {bet["market"] for bet in first.new_bets} == {"OVER_2_5", "BTTS_YES"}
    assert all(bet["expected_value"] >= 0 for bet in first.new_bets)
    assert len(engine.prediction_store.load()) == 3
    assert first.telemetry["funnel"] == {"discovered": 1, "eligible": 1, "modelled": 1, "predictions": 3, "candidates": 2, "selections": 2}
    assert first.telemetry["fixtures_without_odds"] == 0

    second = engine.generate(now)
    assert second.new_bets == ()
    assert len(engine.bet_store.load()) == 2
    assert second.telemetry["funnel"]["discovered"] == 1
    assert second.telemetry["funnel"]["eligible"] == 0
    assert second.telemetry["funnel"]["modelled"] == 0
    assert second.telemetry["funnel"]["predictions"] == 0
    assert second.telemetry["funnel"]["candidates"] == 0
    assert second.telemetry["funnel"]["selections"] == 0


def test_live_mode_refuses_unvalidated_probabilities(settings, monkeypatch) -> None:
    monkeypatch.setenv("PAPER_MODE", "false")
    monkeypatch.setenv("ALLOW_UNCALIBRATED_LIVE", "false")
    live_settings = Settings.from_env(settings.root)
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    with pytest.raises(RuntimeError, match="LIVE režim odbijen"):
        QuantEngine(live_settings, api=FakeAPI(now)).generate(now)


def test_model_cache_is_scoped_to_data_cutoff(settings) -> None:
    now = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    engine = QuantEngine(settings, api=FakeAPI(now))
    fields = {"league_id": 39, "season": 2026, "home_id": 1, "away_id": 2}
    first = engine._model_for_fixture(fields, data_cutoff=now)
    second = engine._model_for_fixture(fields, data_cutoff=now + timedelta(hours=1))
    assert first is not second
    assert len(engine._model_cache) == 2
