import json
from datetime import UTC, datetime

import pytest

from tools.signal_writer_guard import assert_not_stale, build_metadata, is_stale


def test_newer_writer_wins_even_when_timestamp_is_older():
    candidate = build_metadata(
        run_id=200,
        run_attempt=1,
        workflow="watchlist",
        sha="new",
        generated_at=datetime(2026, 9, 9, 20, 0, tzinfo=UTC),
    )
    current = build_metadata(
        run_id=201,
        run_attempt=1,
        workflow="watchlist",
        sha="current",
        generated_at=datetime(2026, 9, 9, 19, 59, tzinfo=UTC),
    )
    assert is_stale(candidate, current)
    assert not is_stale(current, candidate)


def test_first_writer_is_allowed():
    candidate = build_metadata(
        run_id=100,
        run_attempt=1,
        workflow="watchlist",
        sha="first",
    )
    assert not is_stale(candidate, None)


def test_malformed_existing_authority_fails_closed():
    candidate = build_metadata(
        run_id=100,
        run_attempt=1,
        workflow="watchlist",
        sha="candidate",
    )
    assert is_stale(candidate, {"run_id": "not-a-number"})


def test_assert_not_stale_rejects_older_candidate(tmp_path):
    candidate_path = tmp_path / "candidate.json"
    current_path = tmp_path / "current.json"
    candidate_path.write_text(
        json.dumps(
            build_metadata(run_id=10, run_attempt=1, workflow="watchlist", sha="old")
        ),
        encoding="utf-8",
    )
    current_path.write_text(
        json.dumps(
            build_metadata(run_id=11, run_attempt=1, workflow="watchlist", sha="new")
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Stale watchlist writer rejected"):
        assert_not_stale(candidate_path, current_path)


def test_assert_not_stale_allows_newer_candidate(tmp_path):
    candidate_path = tmp_path / "candidate.json"
    current_path = tmp_path / "current.json"
    candidate_path.write_text(
        json.dumps(
            build_metadata(run_id=12, run_attempt=1, workflow="watchlist", sha="new")
        ),
        encoding="utf-8",
    )
    current_path.write_text(
        json.dumps(
            build_metadata(run_id=11, run_attempt=1, workflow="watchlist", sha="old")
        ),
        encoding="utf-8",
    )
    assert_not_stale(candidate_path, current_path)
