import json

import pytest

from tools.provenance_publish_guard import assert_publishable, is_stale, source_run_id


def evidence(run_id: int) -> dict:
    return {"source_run": {"run_id": str(run_id)}}


def test_newer_source_run_can_publish():
    assert not is_stale(20, evidence(19))


def test_older_source_run_is_stale():
    assert is_stale(18, evidence(19))


def test_equal_source_run_is_idempotent():
    assert not is_stale(19, evidence(19))


def test_malformed_existing_evidence_fails_closed(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(RuntimeError, match="malformed"):
        assert_publishable(20, path)


def test_missing_existing_evidence_allows_first_publication(tmp_path):
    path = tmp_path / "evidence.json"
    assert_publishable(20, path)


def test_source_run_id_is_read_from_canonical_shape():
    assert source_run_id(evidence(42)) == 42
    assert source_run_id({"source_run": {"run_id": "bad"}}) is None


def test_publishable_older_evidence_is_rejected(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence(50)), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Stale Strong Signal evidence"):
        assert_publishable(49, path)
