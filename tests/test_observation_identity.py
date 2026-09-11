from datetime import UTC, datetime, timedelta

from quantbot.observation_identity import canonical_observation_id
from quantbot.persistence import OddsSnapshotStore
from quantbot.types import Market, OddsQuote


def test_quote_state_identity_is_stable_across_time_and_lifecycle() -> None:
    first = canonical_observation_id(
        fixture_id=1549016,
        market="BTTS_YES",
        bookmaker_id=8,
        selection="BTTS_YES",
        odd=1.95,
        opposite_odd=1.80,
    )
    second = canonical_observation_id(
        fixture_id=1549016,
        market="BTTS_YES",
        bookmaker_id=8,
        selection="BTTS_YES",
        odd=1.95001,
        opposite_odd=1.80001,
    )
    assert first == second


def test_quote_state_identity_changes_when_price_changes() -> None:
    first = canonical_observation_id(
        fixture_id=1549016,
        market="BTTS_YES",
        bookmaker_id=8,
        selection="BTTS_YES",
        odd=1.95,
        opposite_odd=1.80,
    )
    changed = canonical_observation_id(
        fixture_id=1549016,
        market="BTTS_YES",
        bookmaker_id=8,
        selection="BTTS_YES",
        odd=1.91,
        opposite_odd=1.91,
    )
    assert first != changed


def test_snapshot_store_keeps_same_quote_state_as_distinct_immutable_records(tmp_path) -> None:
    store = OddsSnapshotStore(tmp_path / "odds_snapshots.jsonl")
    base = datetime(2026, 9, 11, 10, tzinfo=UTC)
    first = store.append_quote(
        OddsQuote(Market.BTTS_YES, 1.95, 1.80, 8, "Bet365", base),
        fixture_id=1549016,
        snapshot_type="ENTRY",
    )
    second = store.append_quote(
        OddsQuote(Market.BTTS_YES, 1.95, 1.80, 8, "Bet365", base + timedelta(minutes=5)),
        fixture_id=1549016,
        snapshot_type="INTERMEDIATE",
    )
    assert first is not None
    assert second is not None
    assert first != second
    rows = store.load()
    assert len(rows) == 2
    assert rows[0]["observation_id"] == rows[1]["observation_id"]
    assert rows[0]["snapshot_id"] != rows[1]["snapshot_id"]


def test_legacy_snapshot_is_enriched_in_memory_without_rewrite(tmp_path) -> None:
    path = tmp_path / "odds_snapshots.jsonl"
    path.write_text(
        '{"fixture_id":1549016,"market":"BTTS_YES","bookmaker_id":8,"selection":"BTTS_YES","odd":1.95,"opposite_odd":1.8,"odds_captured_at":"2026-09-11T10:00:00+00:00","snapshot_type":"ENTRY","snapshot_id":"legacy"}\n',
        encoding="utf-8",
    )
    before = path.read_text(encoding="utf-8")
    rows = OddsSnapshotStore(path).load()
    after = path.read_text(encoding="utf-8")
    assert rows[0]["observation_id"]
    assert rows[0]["observation_identity_version"] == 1
    assert before == after
