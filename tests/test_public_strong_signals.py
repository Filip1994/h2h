from __future__ import annotations

import json

from tools.build_public_strong_signals import build_public_strong_signals


def write_json(root, name, value):
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def test_build_public_strong_signals_merges_and_preserves_lifecycle(tmp_path) -> None:
    write_json(
        tmp_path,
        "strong_signals.json",
        [{"id": "signal-1", "status": "PENDING", "odd": 1.90}],
    )
    write_json(
        tmp_path,
        "intraday_alerts.json",
        [
            {
                "id": "signal-1",
                "status": "WIN",
                "profit": 450,
                "signal_sent_at": "2026-09-07T18:00:00+00:00",
            },
            {
                "id": "signal-2",
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
                "status": "WIN",
                "profit": 300,
            },
            {
                "id": "ignored",
                "signal_source": "DAILY_BULLETIN",
                "status": "WIN",
                "profit": 999,
            },
        ],
    )

    data = build_public_strong_signals(tmp_path)

    assert [item["id"] for item in data] == ["signal-1", "signal-2"]
    assert data[0]["status"] == "WIN"
    assert data[0]["virtual_profit"] == 450
    assert data[1]["status"] == "WIN"
    assert data[1]["virtual_profit"] == 300
    assert (
        json.loads((tmp_path / "strong_signals.json").read_text(encoding="utf-8"))
        == data
    )


def test_build_public_strong_signals_is_safe_with_missing_inputs(tmp_path) -> None:
    data = build_public_strong_signals(tmp_path)
    assert data == []
    assert json.loads((tmp_path / "strong_signals.json").read_text(encoding="utf-8")) == []
