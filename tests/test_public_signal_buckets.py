from __future__ import annotations

import json

from tools.build_public_signal_buckets import build


def test_public_buckets_migrate_history_and_keep_strong_ledger_separate(tmp_path) -> None:
    (tmp_path / "strong_signals.json").write_text(
        json.dumps(
            [
                {
                    "id": "strong-1",
                    "signal_class": "STRONG_SIGNAL",
                    "status": "WIN",
                    "profit": 240.0,
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
    # A Production ledger row must never become Strong Signal history.
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
    ledger = json.loads((tmp_path / "strong_signal_ledger.json").read_text(encoding="utf-8"))
    assert [x["id"] for x in ledger] == ["strong-1", "strong-2"]


def test_missing_observation_ledger_does_not_create_fake_near_miss(tmp_path) -> None:
    for name in ("strong_signals.json", "intraday_alerts.json", "bets.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    strong, near = build(tmp_path)
    assert strong == []
    assert near == []
