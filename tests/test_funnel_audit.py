from __future__ import annotations

import json

from tools.funnel_audit import build_audit


def test_funnel_audit_reconciles_selected_predictions(tmp_path) -> None:
    (tmp_path / "generation_health.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "timestamp": "2026-09-09T21:00:00+00:00",
                "status": "HEALTHY",
                "observation_only": True,
                "pipeline": {
                    "fixtures_discovered": 10,
                    "fixtures_eligible": 6,
                    "fixtures_modelled": 5,
                    "predictions_generated": 15,
                    "candidates_qualified": 3,
                    "risk_checks": 3,
                    "selections_produced": 2,
                    "duplicate_rejections": 1,
                    "persistence_failures": 0,
                },
                "funnel": {
                    "discovered": 10,
                    "eligible": 6,
                    "modelled": 5,
                    "predictions": 15,
                    "odds_available": 4,
                    "valid_quotes": 8,
                    "candidates": 3,
                    "ev_pass": 4,
                    "edge_pass": 3,
                    "risk_checks": 3,
                    "selected": 2,
                    "persisted_bets": 2,
                    "settled": 0,
                },
                "funnel_rejections": [
                    {
                        "fixture_id": 1,
                        "stage": "strategy",
                        "reason": "REJECT_LOW_EV",
                    },
                    {
                        "fixture_id": 2,
                        "stage": "risk_staking",
                        "reason": "RISK_OR_CAPACITY",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "predictions.json").write_text(
        json.dumps(
            [
                {"id": "p1", "selected": True},
                {"id": "p2", "selected": True},
                {"id": "p3", "selected": False},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "bets.json").write_text(
        json.dumps([{"prediction_id": "p1"}, {"prediction_id": "p2"}]),
        encoding="utf-8",
    )

    audit = build_audit(tmp_path)
    assert audit["rejection_reason_counts"] == {
        "REJECT_LOW_EV": 1,
        "RISK_OR_CAPACITY": 1,
    }
    assert audit["selected_prediction_count_from_artifact"] == 2
    assert audit["selected_not_persisted"] == []
    assert all(audit["reconciliation"].values())


def test_funnel_audit_exposes_unpersisted_selection(tmp_path) -> None:
    (tmp_path / "generation_health.json").write_text(
        json.dumps(
            {
                "status": "HEALTHY",
                "pipeline": {},
                "funnel": {"discovered": 1, "eligible": 1, "modelled": 1},
                "funnel_rejections": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "predictions.json").write_text(
        json.dumps([{"id": "p1", "selected": True}]), encoding="utf-8"
    )
    (tmp_path / "bets.json").write_text("[]", encoding="utf-8")

    audit = build_audit(tmp_path)
    assert audit["selected_not_persisted"] == ["p1"]
    assert audit["reconciliation"]["selected_predictions_persisted"] is False
