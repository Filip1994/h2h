from __future__ import annotations

import json

from tools.build_public_strong_signals import build_public_strong_signals


def write_json(root, name, value):
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def test_legacy_builder_uses_isolated_strong_signal_contract(tmp_path) -> None:
    write_json(
        tmp_path,
        "strong_signals.json",
        [{"id": "signal-1", "status": "WIN", "profit": 450, "odd": 1.90}],
    )
    write_json(
        tmp_path,
        "intraday_alerts.json",
        [
            {
                "id": "signal-1",
                "signal_class": "STRONG_SIGNAL",
                "status": "WIN",
                "profit": 450,
                "signal_sent_at": "2026-09-07T18:00:00+00:00",
            },
            {
                "id": "signal-2",
                "signal_class": "STRONG_SIGNAL",
                "status": "PENDING",
                "signal_sent_at": "2026-09-07T18:05:00+00:00",
            },
        ],
    )
    write_json(
        tmp_path,
        "bets.json",
        [
            {
                "id": "signal-2",
                "signal_source": "INTRADAY_ALERT",
                "signal_class": "STRONG_SIGNAL",
                "status": "WIN",
                "profit": 300,
            },
            {
                "id": "ignored",
                "signal_source": "DAILY_BULLETIN",
                "signal_class": "STRONG_SIGNAL",
                "status": "WIN",
                "profit": 999,
            },
        ],
    )

    data = build_public_strong_signals(tmp_path)

    assert [item["id"] for item in data] == ["signal-1", "signal-2"]
    assert all(item["virtual_portfolio"] == "STRONG_SIGNALS_VIRTUAL" for item in data)
    assert all(item["not_a_production_bet"] is True for item in data)
    assert all(item["status"] == "PENDING" for item in data)
    assert all(item["virtual_profit"] == 0.0 for item in data)
    assert (
        json.loads((tmp_path / "strong_signals.json").read_text(encoding="utf-8"))
        == data
    )
    portfolio = json.loads(
        (tmp_path / "strong_signals_portfolio.json").read_text(encoding="utf-8")
    )
    assert portfolio["current_bank"] == 10_000.0
    assert portfolio["completed_count"] == 0


def test_legacy_builder_is_safe_with_missing_inputs(tmp_path) -> None:
    data = build_public_strong_signals(tmp_path)
    assert data == []
    assert (
        json.loads((tmp_path / "strong_signals.json").read_text(encoding="utf-8")) == []
    )
