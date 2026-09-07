import json
from datetime import UTC, datetime, timedelta

from quantbot.closing import capture_five_minute_closing_quotes
from quantbot.persistence import OddsSnapshotStore, record_prediction_quote
from quantbot.types import Market, OddsQuote


def quote(at="2026-09-08T10:00:00+00:00", odd=2.0):
    return OddsQuote(Market.OVER_25, odd, 1.8, 10, "Book", datetime.fromisoformat(at))


def test_unique_identity_and_duplicate_api_response(tmp_path):
    store = OddsSnapshotStore(tmp_path / "odds_snapshots.jsonl")
    first = store.append_quote(
        quote(),
        fixture_id=1,
        snapshot_type="INTERMEDIATE",
        prediction_id="p1",
        signal_id="p1",
    )
    duplicate = store.append_quote(
        quote(),
        fixture_id=1,
        snapshot_type="INTERMEDIATE",
        prediction_id="p1",
        signal_id="p1",
    )
    assert first and duplicate is None
    assert len((tmp_path / "odds_snapshots.jsonl").read_text().splitlines()) == 1


def test_identical_odds_at_different_times_are_distinct(tmp_path):
    store = OddsSnapshotStore(tmp_path / "odds_snapshots.jsonl")
    a = store.append_quote(quote(), fixture_id=1, snapshot_type="INTERMEDIATE")
    b = store.append_quote(
        quote("2026-09-08T10:05:00+00:00"),
        fixture_id=1,
        snapshot_type="INTERMEDIATE",
    )
    assert a != b


def test_stable_prediction_and_bet_linkage(tmp_path):
    class Settings:
        root = tmp_path

    prediction = {
        "id": "p1",
        "event_id": 1,
        "market": "OVER_2_5",
        "odd": 2.0,
        "opposite_odd": 1.8,
        "bookmaker_id": 10,
        "bookmaker": "Book",
        "odds_captured_at": "2026-09-08T10:00:00+00:00",
        "signal_id": "p1",
    }
    sid = record_prediction_quote(Settings, prediction, bet_id="b1")
    record = json.loads((tmp_path / "data" / "odds_snapshots.jsonl").read_text())
    assert sid == record["snapshot_id"]
    assert record["prediction_id"] == "p1"
    assert record["bet_id"] == "b1"
    assert record["signal_id"] == "p1"


def test_rejected_signal_without_bet_and_missing_bookmaker(tmp_path):
    class Settings:
        root = tmp_path

    prediction = {
        "id": "p-rejected",
        "event_id": 2,
        "market": "UNDER_2_5",
        "odd": 1.7,
        "opposite_odd": 2.1,
        "bookmaker_id": 10,
        "bookmaker": "Book",
        "odds_captured_at": "2026-09-08T10:00:00+00:00",
    }
    assert record_prediction_quote(Settings, prediction, bet_id=None)
    missing = dict(prediction, id="p-missing", odd=None)
    assert record_prediction_quote(Settings, missing) is None


def test_immutable_entry_and_closing_types(tmp_path):
    store = OddsSnapshotStore(tmp_path / "odds_snapshots.jsonl")
    entry = store.append_quote(
        quote(), fixture_id=1, snapshot_type="ENTRY", prediction_id="p1"
    )
    assert (
        store.append_quote(
            quote("2026-09-08T10:00:00+00:00", 2.2),
            fixture_id=1,
            snapshot_type="ENTRY",
            prediction_id="p1",
        )
        is not None
    )
    closing = store.append_quote(
        quote("2026-09-08T10:55:00+00:00", 1.9),
        fixture_id=1,
        snapshot_type="CLOSING",
        prediction_id="p1",
        bet_id="b1",
    )
    records = [
        json.loads(x)
        for x in (tmp_path / "odds_snapshots.jsonl").read_text().splitlines()
    ]
    assert records[0]["snapshot_id"] == entry
    assert records[-1]["snapshot_id"] == closing
    assert {r["snapshot_type"] for r in records} == {"ENTRY", "CLOSING"}


def test_missing_t5_is_not_fabricated(tmp_path):
    store = OddsSnapshotStore(tmp_path / "odds_snapshots.jsonl")
    assert store.append_quote(quote(), fixture_id=1, snapshot_type="INTERMEDIATE")
    records = [
        json.loads(x)
        for x in (tmp_path / "odds_snapshots.jsonl").read_text().splitlines()
    ]
    assert all(r["snapshot_type"] != "T5" for r in records)


def test_t5_capture_window(monkeypatch, tmp_path):
    class Settings:
        bets_file = tmp_path / "bets.json"
        max_market_overround = 0.25

    now = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    bet = {
        "id": "b1",
        "status": "PENDING",
        "kickoff": (now + timedelta(minutes=5)).isoformat(),
        "event_id": 1,
        "market": "OVER_2_5",
        "bookmaker_id": 10,
    }

    class FakeStore:
        def __init__(self, _path):
            self.data = [dict(bet)]

        def load(self):
            return self.data

        def save(self, data):
            self.data = data

    class FakeAPI:
        def __init__(self, _settings):
            pass

        def odds(self, _fixture_id):
            return []

    monkeypatch.setattr("quantbot.closing.BetStore", FakeStore)
    monkeypatch.setattr("quantbot.closing.APIFootballClient", FakeAPI)
    monkeypatch.setattr(
        "quantbot.closing.extract_best_quotes",
        lambda *args, **kwargs: {
            Market.OVER_25: quote(now.isoformat())
        },
    )

    assert capture_five_minute_closing_quotes(Settings, now) == 1

    outside = now + timedelta(minutes=4)
    assert capture_five_minute_closing_quotes(Settings, outside) == 0


def test_clv_formula_correctness(tmp_path):
    store = OddsSnapshotStore(tmp_path / "odds_snapshots.jsonl")
    store.append_quote(
        quote("2026-09-08T10:00:00+00:00", 2.0),
        fixture_id=1,
        snapshot_type="ENTRY",
        prediction_id="p1",
    )
    store.append_quote(
        quote("2026-09-08T10:55:00+00:00", 1.9),
        fixture_id=1,
        snapshot_type="CLOSING",
        prediction_id="p1",
        bet_id="b1",
    )
    records = [
        json.loads(x)
        for x in (tmp_path / "odds_snapshots.jsonl").read_text().splitlines()
    ]
    entry, closing = records
    assert round(entry["odd"] / closing["odd"] - 1, 6) == 0.052632
    assert (
        round(closing["devig_probability"] - entry["devig_probability"], 6)
        == 0.012802
    )
