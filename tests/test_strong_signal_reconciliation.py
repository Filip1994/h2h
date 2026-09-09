from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.reconcile_strong_signal_run import build_evidence


def _git_show(monkeypatch, root: Path, payload: str) -> None:
    def fake_check_output(command, cwd=None, text=None):
        assert cwd == root
        return payload

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)


def test_reconciles_zero_new_signals(tmp_path: Path, monkeypatch) -> None:
    existing = [
        {"id": "old", "signal_class": "STRONG_SIGNAL", "status": "WIN", "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL", "not_a_production_bet": True},
    ]
    (tmp_path / "strong_signals.json").write_text(json.dumps(existing), encoding="utf-8")
    _git_show(monkeypatch, tmp_path, json.dumps(existing))

    evidence = build_evidence(tmp_path)
    assert evidence["strong_signal_provenance"]["new_strong_signals"] == 0
    assert evidence["strong_signal_provenance"]["new_strong_signal_ids"] == []
    assert evidence["reconciliation"]["dataset_delta_equals_new_strong_signals"] is True


def test_reconciles_one_new_signal(tmp_path: Path, monkeypatch) -> None:
    existing = [
        {"id": "old", "signal_class": "STRONG_SIGNAL", "status": "LOSS", "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL", "not_a_production_bet": True},
    ]
    current = existing + [
        {"id": "new-1", "signal_class": "STRONG_SIGNAL", "status": "PENDING", "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL", "not_a_production_bet": True},
    ]
    (tmp_path / "strong_signals.json").write_text(json.dumps(current), encoding="utf-8")
    _git_show(monkeypatch, tmp_path, json.dumps(existing))

    evidence = build_evidence(tmp_path)
    assert evidence["strong_signal_provenance"]["new_strong_signals"] == 1
    assert evidence["strong_signal_provenance"]["new_strong_signal_ids"] == ["new-1"]
    assert evidence["reconciliation"]["dataset_delta_equals_new_strong_signals"] is True
    assert evidence["reconciliation"]["no_new_signal_id_missing_from_public"] is True


def test_terminal_new_signal_is_history_not_active(tmp_path: Path, monkeypatch) -> None:
    existing = []
    current = [
        {"id": "new-1", "signal_class": "STRONG_SIGNAL", "status": "SKIPPED", "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL", "not_a_production_bet": True},
    ]
    (tmp_path / "strong_signals.json").write_text(json.dumps(current), encoding="utf-8")
    _git_show(monkeypatch, tmp_path, json.dumps(existing))

    evidence = build_evidence(tmp_path)
    proof = evidence["strong_signal_provenance"]
    assert proof["active_strong_signals"] == 0
    assert proof["history_strong_signals"] == 1
    assert evidence["reconciliation"]["history_excludes_pending"] is True


def test_public_ids_must_be_unique(tmp_path: Path, monkeypatch) -> None:
    existing = []
    current = [
        {"id": "duplicate", "signal_class": "STRONG_SIGNAL", "status": "PENDING", "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL", "not_a_production_bet": True},
        {"id": "duplicate", "signal_class": "STRONG_SIGNAL", "status": "PENDING", "virtual_portfolio": "STRONG_SIGNALS_VIRTUAL", "not_a_production_bet": True},
    ]
    (tmp_path / "strong_signals.json").write_text(json.dumps(current), encoding="utf-8")
    _git_show(monkeypatch, tmp_path, json.dumps(existing))

    evidence = build_evidence(tmp_path)
    assert evidence["reconciliation"]["public_ids_unique"] is False
