from quantbot.strong_signal_bankroll import STRONG_SIGNAL_INITIAL_BANK, portfolio  # noqa: I001


VIRTUAL = "STRONG_SIGNALS_VIRTUAL"


def test_strong_signal_bankroll_is_independent_from_production() -> None:
    rows = [
        {
            "signal_class": "STRONG_SIGNAL",
            "virtual_portfolio": VIRTUAL,
            "status": "WIN",
            "stake": 100.0,
            "virtual_profit": 90.0,
            "settled_at": "2026-09-08T12:00:00+00:00",
        },
        {
            "signal_class": "STRONG_SIGNAL",
            "status": "LOSS",
            "stake": 5000.0,
            "profit": -5000.0,
        },
        {
            "signal_class": "NEAR_MISS",
            "status": "LOSS",
            "stake": 5000.0,
            "profit": -5000.0,
        },
        {
            "signal_class": "STRONG_SIGNAL",
            "virtual_portfolio": VIRTUAL,
            "status": "PENDING",
            "stake": 100.0,
        },
    ]
    metrics = portfolio(rows)
    assert metrics.initial_bank == STRONG_SIGNAL_INITIAL_BANK == 10_000.0
    assert metrics.current_bank == 10_090.0
    assert metrics.total_profit == 90.0
    assert metrics.total_stake == 100.0
    assert metrics.open_stake == 100.0
    assert metrics.completed_count == 1


def test_strong_signal_bankroll_uses_virtual_profit() -> None:
    metrics = portfolio(
        [
            {
                "signal_class": "STRONG_SIGNAL",
                "virtual_portfolio": VIRTUAL,
                "status": "LOSS",
                "stake": 100.0,
                "profit": -100.0,
                "virtual_profit": -100.0,
                "settled_at": "2026-09-08T12:00:00+00:00",
            }
        ]
    )
    assert metrics.current_bank == 9_900.0
    assert metrics.roi == -1.0
