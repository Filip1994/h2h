from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    path = ROOT / "tools" / "audit_production_targets.py"
    spec = importlib.util.spec_from_file_location("audit_production_targets", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_target_health_is_exact_and_degraded_without_fabrication(tmp_path, monkeypatch):
    module = load_tool()
    bets = [
        {
            "id": "1",
            "event_id": 123,
            "bookmaker_id": 8,
            "bookmaker": "Bet365",
            "market": "UNDER_2_5",
            "selection": "UNDER_2_5",
            "odd": 2.5,
            "kickoff": "2099-01-01T20:00:00+00:00",
            "status": "PENDING",
        }
    ]
    snapshots = [
        {
            "fixture_id": 123,
            "bookmaker_id": 8,
            "market": "UNDER_2_5",
            "selection": "UNDER_2_5",
            "odd": 2.6,
            "odds_captured_at": "2026-01-01T00:00:00+00:00",
            "observation_id": "obs-1",
        }
    ]
    bets_path = tmp_path / "bets.json"
    snapshots_path = tmp_path / "snapshots.jsonl"
    dashboard_path = tmp_path / "dashboard.json"
    out_path = tmp_path / "health.json"
    bets_path.write_text(json.dumps(bets), encoding="utf-8")
    snapshots_path.write_text("\n".join(json.dumps(row) for row in snapshots) + "\n", encoding="utf-8")
    dashboard_path.write_text(json.dumps({}), encoding="utf-8")

    monkeypatch.setattr(module, "BETS", bets_path)
    monkeypatch.setattr(module, "SNAPSHOTS", snapshots_path)
    monkeypatch.setattr(module, "DASHBOARD", dashboard_path)
    monkeypatch.setattr(module, "OUT", out_path)
    assert module.main() == 0

    health = json.loads(out_path.read_text(encoding="utf-8"))
    assert health["overall"] == "DEGRADED"
    assert health["counts"]["stale"] == 1
    assert health["targets"][0]["latest_odd"] == 2.6
    assert health["targets"][0]["status"] == "STALE_TARGET_QUOTE"

    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["monitoring"]["production_quote_health"]["overall"] == "DEGRADED"


def test_missing_exact_target_does_not_use_another_bookmaker(tmp_path, monkeypatch):
    module = load_tool()
    bets = [
        {
            "id": "1",
            "event_id": 123,
            "bookmaker_id": 8,
            "bookmaker": "Bet365",
            "market": "UNDER_2_5",
            "selection": "UNDER_2_5",
            "odd": 2.5,
            "kickoff": "2099-01-01T20:00:00+00:00",
            "status": "PENDING",
        }
    ]
    snapshots = [
        {
            "fixture_id": 123,
            "bookmaker_id": 9,
            "market": "UNDER_2_5",
            "selection": "UNDER_2_5",
            "odd": 2.8,
            "odds_captured_at": "2098-01-01T00:00:00+00:00",
        }
    ]
    bets_path = tmp_path / "bets.json"
    snapshots_path = tmp_path / "snapshots.jsonl"
    dashboard_path = tmp_path / "dashboard.json"
    out_path = tmp_path / "health.json"
    bets_path.write_text(json.dumps(bets), encoding="utf-8")
    snapshots_path.write_text(json.dumps(snapshots[0]) + "\n", encoding="utf-8")
    dashboard_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(module, "BETS", bets_path)
    monkeypatch.setattr(module, "SNAPSHOTS", snapshots_path)
    monkeypatch.setattr(module, "DASHBOARD", dashboard_path)
    monkeypatch.setattr(module, "OUT", out_path)

    assert module.main() == 0
    health = json.loads(out_path.read_text(encoding="utf-8"))
    target = health["targets"][0]
    assert target["status"] == "MISSING_TARGET_QUOTE"
    assert target["latest_odd"] is None
