from __future__ import annotations

from datetime import UTC, datetime

import main
from main import persist_intraday_strong_signals


def test_legacy_strong_signal_persistence_hook_is_noop(settings) -> None:
    now = datetime(2026, 9, 7, 16, 30, tzinfo=UTC)
    bet = {
        "id": "bet-strong-001",
        "prediction_id": "pred-001",
        "event_id": 123,
        "market": "OVER_2_5",
        "bookmaker_id": 8,
    }

    original_root = main.ROOT
    main.ROOT = settings.root
    try:
        persist_intraday_strong_signals(settings, (bet,), now)
    finally:
        main.ROOT = original_root

    assert not (settings.root / "intraday_alerts.json").exists()
