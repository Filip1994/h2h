from __future__ import annotations

from datetime import UTC, datetime, timedelta

from quantbot.markets import extract_all_valid_quotes
from quantbot.odds_collection import cadence_minutes, collect


def fixture_payload(fixture_id: int, kickoff: datetime) -> dict:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat(),
            "status": {"short": "NS"},
        },
        "league": {"id": 1, "name": "Test League", "country": "Test", "season": 2026},
        "teams": {
            "home": {"id": 10, "name": "Home"},
            "away": {"id": 11, "name": "Away"},
        },
    }


def odds_payload() -> list[dict]:
    return [
        {
            "bookmakers": [
                {
                    "id": 8,
                    "name": "Bet365",
                    "bets": [
                        {
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 2.5", "odd": "2.10"},
                                {"value": "Under 2.5", "odd": "1.75"},
                            ],
                        },
                        {
                            "name": "Both Teams Score",
                            "values": [
                                {"value": "Yes", "odd": "1.90"},
                                {"value": "No", "odd": "1.90"},
                            ],
                        },
                    ],
                },
                {
                    "id": 11,
                    "name": "1xBet",
                    "bets": [
                        {
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 2.5", "odd": "2.20"},
                                {"value": "Under 2.5", "odd": "1.70"},
                            ],
                        }
                    ],
                },
            ]
        }
    ]


def test_cadence_gets_denser_toward_kickoff():
    assert cadence_minutes(71) == 24 * 60
    assert cadence_minutes(47) == 8 * 60
    assert cadence_minutes(23) == 2 * 60
    assert cadence_minutes(5) == 30
    assert cadence_minutes(2) == 15
    assert cadence_minutes(0.5) == 5


def test_all_valid_quotes_preserves_every_bookmaker_market():
    quotes = extract_all_valid_quotes(odds_payload(), captured_at=datetime.now(UTC))
    identities = {(q.bookmaker_id, q.market.value, q.odd) for q in quotes}
    assert len(quotes) == 4
    assert (8, "OVER_2_5", 2.1) in identities
    assert (8, "BTTS_YES", 1.9) in identities
    assert (11, "OVER_2_5", 2.2) in identities


def test_collector_creates_real_opening_then_intermediate(monkeypatch, settings):
    import quantbot.odds_collection as module

    kickoff = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    now = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)

    class FakeAPI:
        request_count = 0

        def __init__(self, _settings):
            self.request_count = 0

        def fixtures_by_date(self, _date):
            self.request_count += 1
            if _date == "2026-09-12":
                return [fixture_payload(100, kickoff)]
            return []

        def odds(self, fixture_id):
            assert fixture_id == 100
            self.request_count += 1
            return odds_payload()

    monkeypatch.setattr(module, "APIFootballClient", FakeAPI)
    first = collect(settings, now)
    assert first["queried_fixtures"] == 1
    snapshots = (settings.root / "data" / "odds_snapshots.jsonl").read_text()
    assert '"snapshot_type":"OPENING"' in snapshots

    second = collect(settings, now + timedelta(hours=3))
    assert second["queried_fixtures"] == 1
    snapshots = (settings.root / "data" / "odds_snapshots.jsonl").read_text()
    assert '"snapshot_type":"INTERMEDIATE"' in snapshots


def test_collector_records_no_odds_without_fabricating_opening(monkeypatch, settings):
    import quantbot.odds_collection as module

    kickoff = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    now = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)

    class FakeAPI:
        def __init__(self, _settings):
            self.request_count = 0

        def fixtures_by_date(self, _date):
            self.request_count += 1
            return [fixture_payload(101, kickoff)] if _date == "2026-09-10" else []

        def odds(self, _fixture_id):
            self.request_count += 1
            return []

    monkeypatch.setattr(module, "APIFootballClient", FakeAPI)
    result = collect(settings, now)
    assert result["empty_responses"] == 1
    assert result["observations_captured"] == 0
    coverage = (settings.root / "data" / "odds_collection_coverage.jsonl").read_text()
    assert "NO_ODDS_RESPONSE" in coverage
    assert not (settings.root / "data" / "odds_snapshots.jsonl").exists()


def test_daily_budget_is_bounded(monkeypatch, settings):
    import quantbot.odds_collection as module

    settings = type(settings)(**{
        **{field: getattr(settings, field) for field in settings.__dataclass_fields__},
        "api_request_budget": 3,
        "api_budget_reserve": 1,
    })

    kickoff = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    now = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)

    class FakeAPI:
        def __init__(self, _settings):
            self.request_count = 0

        def fixtures_by_date(self, _date):
            self.request_count += 1
            return [fixture_payload(102, kickoff)] if _date == "2026-09-10" else []

        def odds(self, _fixture_id):
            self.request_count += 1
            return odds_payload()

    monkeypatch.setattr(module, "APIFootballClient", FakeAPI)
    result = collect(settings, now)
    budget = __import__("json").loads(
        (settings.root / "odds_collection_budget.json").read_text()
    )
    assert budget["requests_used"] <= budget["working_budget"]
    assert result["daily_budget_used"] <= 2
