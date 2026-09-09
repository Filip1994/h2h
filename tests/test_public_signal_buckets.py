from __future__ import annotations

import json

from tools.build_public_signal_buckets import build


def test_public_buckets_are_separate(tmp_path) -> None:
    (tmp_path / "strong_signals.json").write_text(
        json.dumps([{"id": "strong-1", "signal_class": "STRONG_SIGNAL"}]),
        encoding="utf-8",
    )
    (tmp_path / "intraday_alerts.json").write_text(
        json.dumps(
            [
                {"id": "strong-2", "signal_class": "STRONG_SIGNAL"},
                {"id": "near-alert", "signal_class": "NEAR_MISS"},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "bets.json").write_text("[]", encoding="utf-8")
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
    assert all(x.get("signal_class") == "STRONG_SIGNAL" for x in strong)
    assert all(x.get("signal_class") == "NEAR_MISS" for x in near)
    assert all("profit" in x for x in near)
    assert all(float(x["profit"]) == 0.0 for x in near)


def test_missing_observation_ledger_does_not_create_fake_near_miss(tmp_path) -> None:
    for name in ("strong_signals.json", "intraday_alerts.json", "bets.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    strong, near = build(tmp_path)
    assert strong == []
    assert near == []
