import json
from datetime import datetime

from quantbot.persistence import OddsSnapshotStore
from quantbot.types import Market, OddsQuote
from tools.persist_clv import closing


def _quote(at: str, odd: float) -> OddsQuote:
    return OddsQuote(
        Market.OVER_25,
        odd,
        1.8,
        10,
        "Book",
        datetime.fromisoformat(at),
    )


def _settings(tmp_path):
    class Settings:
        bets_file = tmp_path / "bets.json"

    return Settings


def _write_bet(path, bet):
    path.write_text(json.dumps([bet]))


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_missing_closing_does_not_promote_t5(tmp_path, monkeypatch):
    import tools.persist_clv as module

    snap = tmp_path / "odds_snapshots.jsonl"
    monkeypatch.setattr(module, "SNAP", snap)
    store = OddsSnapshotStore(snap)
    entry = store.append_quote(
        _quote("2026-09-08T09:00:00+00:00", 2.0),
        fixture_id=1,
        snapshot_type="ENTRY",
        prediction_id="p1",
        bet_id="b1",
    )
    t5 = store.append_quote(
        _quote("2026-09-08T09:55:00+00:00", 1.94),
        fixture_id=1,
        snapshot_type="T5",
        prediction_id="p1",
        bet_id="b1",
    )
    _write_bet(
        tmp_path / "bets.json",
        {
            "id": "b1",
            "event_id": 1,
            "market": "OVER_2_5",
            "bookmaker_id": 10,
            "status": "WIN",
            "kickoff": "2026-09-08T10:00:00+00:00",
            "entry_snapshot_id": entry,
            "t5_snapshot_id": t5,
        },
    )
    assert closing(_settings(tmp_path)) == 0
    bet = json.loads((tmp_path / "bets.json").read_text())[0]
    assert bet.get("closing_snapshot_id") is None
    assert bet["clv_status"] == "NOT_COMPUTABLE"
    assert [s["snapshot_type"] for s in _read(snap)] == ["ENTRY", "T5"]


def test_real_closing_is_persisted_and_t5_stays_t5(tmp_path, monkeypatch):
    import tools.persist_clv as module

    snap = tmp_path / "odds_snapshots.jsonl"
    monkeypatch.setattr(module, "SNAP", snap)
    store = OddsSnapshotStore(snap)
    entry = store.append_quote(
        _quote("2026-09-08T09:00:00+00:00", 2.0),
        fixture_id=1,
        snapshot_type="ENTRY",
        prediction_id="p1",
        bet_id="b1",
    )
    t5 = store.append_quote(
        _quote("2026-09-08T09:55:00+00:00", 1.94),
        fixture_id=1,
        snapshot_type="T5",
        prediction_id="p1",
        bet_id="b1",
    )
    _write_bet(
        tmp_path / "bets.json",
        {
            "id": "b1",
            "event_id": 1,
            "market": "OVER_2_5",
            "bookmaker_id": 10,
            "status": "WIN",
            "kickoff": "2026-09-08T10:00:00+00:00",
            "entry_snapshot_id": entry,
            "t5_snapshot_id": t5,
            "closing_odd": 1.90,
            "closing_opposite_odd": 1.80,
            "closing_market_probability_devig": 1 / 1.90 / (1 / 1.90 + 1 / 1.80),
            "closing_odds_captured_at": "2026-09-08T09:59:30+00:00",
        },
    )
    assert closing(_settings(tmp_path)) == 1
    bet = json.loads((tmp_path / "bets.json").read_text())[0]
    rows = _read(snap)
    closing_rows = [s for s in rows if s["snapshot_type"] == "CLOSING"]
    assert len(closing_rows) == 1
    assert closing_rows[0]["odd"] == 1.9
    assert closing_rows[0]["prediction_id"] == "p1"
    assert closing_rows[0]["signal_id"] == "p1"
    assert bet["t5_snapshot_id"] == t5
    assert bet["closing_snapshot_id"] == closing_rows[0]["snapshot_id"]
    assert bet["clv_odds_pct"] == round(2.0 / 1.9 - 1, 6)
    assert bet["clv_status"] == "COMPUTABLE"
    assert sum(s["snapshot_type"] == "T5" for s in rows) == 1


def test_intermediate_and_t5_can_never_be_promoted(tmp_path, monkeypatch):
    import tools.persist_clv as module

    snap = tmp_path / "odds_snapshots.jsonl"
    monkeypatch.setattr(module, "SNAP", snap)
    store = OddsSnapshotStore(snap)
    for snapshot_type, odd, captured in (
        ("ENTRY", 2.0, "09:00:00"),
        ("INTERMEDIATE", 1.96, "09:30:00"),
        ("T5", 1.94, "09:55:00"),
    ):
        store.append_quote(
            _quote(f"2026-09-08T{captured}+00:00", odd),
            fixture_id=1,
            snapshot_type=snapshot_type,
        )
    _write_bet(
        tmp_path / "bets.json",
        {
            "id": "b1",
            "event_id": 1,
            "market": "OVER_2_5",
            "bookmaker_id": 10,
            "status": "LOSS",
            "kickoff": "2026-09-08T10:00:00+00:00",
        },
    )
    assert closing(_settings(tmp_path)) == 0
    rows = _read(snap)
    assert all(s["snapshot_type"] != "CLOSING" for s in rows)
    assert {s["snapshot_type"] for s in rows} == {
        "ENTRY",
        "INTERMEDIATE",
        "T5",
    }


def test_decision_fields_are_untouched(tmp_path, monkeypatch):
    import tools.persist_clv as module

    snap = tmp_path / "odds_snapshots.jsonl"
    monkeypatch.setattr(module, "SNAP", snap)
    store = OddsSnapshotStore(snap)
    entry = store.append_quote(
        _quote("2026-09-08T09:00:00+00:00", 2.0),
        fixture_id=1,
        snapshot_type="ENTRY",
        prediction_id="p1",
        bet_id="b1",
    )
    decision = {
        "market": "OVER_2_5",
        "odd": 2.0,
        "model_probability": 0.58,
        "calibrated_probability": 0.57,
        "ev": 0.14,
        "edge": 0.08,
        "h2h": {"enabled": True},
        "stake": 1200,
        "risk": "PAPER",
    }
    bet = {
        "id": "b1",
        "event_id": 1,
        "market": "OVER_2_5",
        "bookmaker_id": 10,
        "status": "WIN",
        "kickoff": "2026-09-08T10:00:00+00:00",
        "entry_snapshot_id": entry,
        **decision,
        "closing_odd": 1.90,
        "closing_opposite_odd": 1.80,
        "closing_market_probability_devig": 0.5,
        "closing_odds_captured_at": "2026-09-08T09:59:30+00:00",
    }
    _write_bet(tmp_path / "bets.json", bet)
    before = {key: bet[key] for key in decision}
    assert closing(_settings(tmp_path)) == 1
    after = json.loads((tmp_path / "bets.json").read_text())[0]
    assert {key: after[key] for key in decision} == before
