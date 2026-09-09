from __future__ import annotations

import json

from src.quantbot.strong_signal_bankroll import portfolio
from tools.build_public_signal_buckets import build


def test_public_buckets_restore_frozen_history_and_keep_strong_ledger_separate(
    tmp_path,
) -> None:
    (tmp_path / "strong_signals.json").write_text(
        json.dumps(
            [
                {
                    "id": "strong-1",
                    "signal_class": "STRONG_SIGNAL",
                    "status": "PENDING",
                    "profit": 0.0,
                },
                {
                    "id": "strong-2",
                    "signal_class": "STRONG_SIGNAL",
                    "status": "PENDING",
                    "profit": 0.0,
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "strong_signal_legacy_settlements.json").write_text(
        json.dumps(
            [
                {
                    "id": "strong-1",
                    "status": "WIN",
                    "profit": 240.0,
                    "result": "1:0",
                    "settled_at": "2026-09-09T10:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "intraday_alerts.json").write_text(
        json.dumps(
            [
                {
                    "id": "strong-2",
                    "signal_class": "STRONG_SIGNAL",
                    "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL",
                    "status": "LOSS",
                    "profit": -100.0,
                },
                {"id": "near-alert", "signal_class": "NEAR_MISS"},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "bets.json").write_text(
        json.dumps(
            [
                {
                    "id": "production-only",
                    "signal_source": "INTRADAY_ALERT",
                    "signal_class": "STRONG_SIGNAL",
                    "status": "WIN",
                    "profit": 9999.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    data = (
        '{"observation_id":"near-1","prediction_id":"p1",'
        '"fixture_id":1,"market":"UNDER_2_5","signal_class":"NEAR_MISS",'
        '"captured_at":"2026-09-09T10:00:00+00:00"}\n'
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "market_timing_snapshots.jsonl").write_text(
        data, encoding="utf-8"
    )

    strong, near = build(tmp_path)
    assert [x["id"] for x in strong] == ["strong-1", "strong-2"]
    assert [x["id"] for x in near] == ["near-1"]
    assert all(x["signal_class"] == "STRONG_SIGNAL" for x in strong)
    assert all(x["virtual_portfolio"] == "STRONG_SIGNALS_VIRTUAL" for x in strong)
    assert all(x["not_a_production_bet"] is True for x in strong)
    assert all(x["signal_class"] == "NEAR_MISS" for x in near)
    assert all("profit" in x for x in near)
    assert all(float(x["profit"]) == 0.0 for x in near)
    assert not any(x["id"] == "production-only" for x in strong)
    assert strong[0]["status"] == "WIN"
    assert strong[0]["virtual_settled"] is True
    assert strong[0]["virtual_profit"] == 240.0
    assert strong[1]["status"] == "PENDING"
    assert strong[1]["virtual_settled"] is False
    assert strong[1]["virtual_profit"] == 0.0
    metrics = portfolio(strong)
    assert metrics.initial_bank == 10_000.0
    assert metrics.current_bank == 10_240.0
    assert metrics.total_profit == 240.0
    assert metrics.completed_count == 1
    ledger = json.loads(
        (tmp_path / "strong_signal_ledger.json").read_text(encoding="utf-8")
    )
    assert [x["id"] for x in ledger] == ["strong-1", "strong-2"]


def test_skipped_strong_signal_stays_historical_and_not_active(tmp_path) -> None:
    (tmp_path / "strong_signal_ledger.json").write_text(
        json.dumps(
            [
                {
                    "id": "tz-skipped",
                    "signal_class": "STRONG_SIGNAL",
                    "status": "PENDING",
                    "profit": 0.0,
                    "virtual_settled": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "strong_signals.json").write_text("[]", encoding="utf-8")
    (tmp_path / "intraday_alerts.json").write_text(
        json.dumps(
            [
                {
                    "id": "tz-skipped",
                    "signal_class": "STRONG_SIGNAL",
                    "status": "SKIPPED",
                    "profit": 0.0,
                    "league": "Tanzania - Ligi kuu Bara",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "bets.json").write_text("[]", encoding="utf-8")
    strong, _ = build(tmp_path)
    assert len(strong) == 1
    assert strong[0]["status"] == "SKIPPED"
    assert strong[0]["virtual_settled"] is False
    assert strong[0]["virtual_profit"] == 0.0
    assert strong[0]["league"] == "Tanzania - Ligi kuu Bara"


def test_explicit_virtual_settlement_is_the_only_source_of_signal_profit() -> None:
    rows = [
        {
            "id": "linked-production",
            "signal_class": "STRONG_SIGNAL",
            "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL",
            "status": "WIN",
            "profit": 500.0,
            "virtual_profit": 500.0,
            "linked_bet_id": "production-1",
        },
        {
            "id": "real-virtual",
            "signal_class": "STRONG_SIGNAL",
            "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL",
            "status": "WIN",
            "profit": 200.0,
            "virtual_profit": 200.0,
            "virtual_settled": True,
            "stake": 500.0,
        },
    ]
    metrics = portfolio(rows)
    assert metrics.total_profit == 200.0
    assert metrics.current_bank == 10_200.0
    assert metrics.completed_count == 1


def test_missing_observation_ledger_does_not_create_fake_near_miss(tmp_path) -> None:
    for name in ("strong_signals.json", "intraday_alerts.json", "bets.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    strong, near = build(tmp_path)
    assert strong == []
    assert near == []
