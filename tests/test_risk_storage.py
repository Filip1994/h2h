from quantbot.risk import circuit_breaker_multiplier, kelly_stake, portfolio_analytics
from quantbot.storage import BetStore


def test_kelly_is_capped_and_never_forces_negative_ev(settings) -> None:
    assert kelly_stake(50_000, 0.75, 1.45, settings) == 500
    assert kelly_stake(50_000, 0.50, 1.80, settings) == 0


def test_circuit_breaker_uses_equity_drawdown(settings) -> None:
    bets = [
        {"status": "WIN", "stake": 1_000, "profit": 1_000, "date": "2026-01-01"},
        {"status": "LOSS", "stake": 6_000, "profit": -6_000, "date": "2026-01-02"},
    ]
    analytics = portfolio_analytics(bets, 50_000)
    assert analytics.current_bank == 45_000
    assert analytics.current_drawdown > 0.10
    assert circuit_breaker_multiplier(analytics.current_drawdown, settings) == 0.0


def test_store_blocks_fixture_across_all_statuses(settings) -> None:
    store = BetStore(settings.bets_file)
    store.save([{"id": "old", "event_id": 7, "status": "SKIPPED"}])
    appended = store.append_unique_fixtures(
        [
            {"id": "same-fixture-new-market", "event_id": 7, "status": "PENDING"},
            {"id": "new", "event_id": 8, "status": "PENDING"},
        ]
    )
    assert [item["event_id"] for item in appended] == [8]
    assert len(store.load()) == 2
