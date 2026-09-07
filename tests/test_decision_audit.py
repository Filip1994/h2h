from __future__ import annotations

import json

from tools.decision_audit import append_current_state


def test_decision_audit_is_append_only(tmp_path, monkeypatch):
    predictions = tmp_path / "predictions.json"
    bets = tmp_path / "bets.json"
    audit = tmp_path / "audit.jsonl"
    predictions.write_text(
        json.dumps([{"id": "p1", "selected": False, "rejection_reason": "REJECT_LOW_EV"}]),
        encoding="utf-8",
    )
    bets.write_text(json.dumps([{"id": "b1", "status": "PENDING"}]), encoding="utf-8")
    monkeypatch.setattr("tools.decision_audit.SOURCES", (("PREDICTION", predictions), ("BET", bets)))
    monkeypatch.setattr("tools.decision_audit.AUDIT_FILE", audit)

    assert append_current_state() == 2
    assert append_current_state() == 0
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert {json.loads(line)["event_type"] for line in lines} == {"PREDICTION", "BET"}


def test_decision_audit_records_state_transition(tmp_path, monkeypatch):
    predictions = tmp_path / "predictions.json"
    bets = tmp_path / "bets.json"
    audit = tmp_path / "audit.jsonl"
    predictions.write_text(json.dumps([{"id": "p1", "status": "PENDING"}]), encoding="utf-8")
    bets.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("tools.decision_audit.SOURCES", (("PREDICTION", predictions), ("BET", bets)))
    monkeypatch.setattr("tools.decision_audit.AUDIT_FILE", audit)

    assert append_current_state() == 1
    predictions.write_text(json.dumps([{"id": "p1", "status": "SETTLED", "outcome": 1}]), encoding="utf-8")
    assert append_current_state() == 1
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [event["record"]["status"] for event in events] == ["PENDING", "SETTLED"]
