from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def build_audit(root: Path = ROOT) -> dict[str, Any]:
    health = _load(root / "generation_health.json", {})
    predictions = _load(root / "predictions.json", [])
    bets = _load(root / "bets.json", [])

    if not isinstance(health, dict):
        raise RuntimeError("generation_health.json is not an object")
    if not isinstance(predictions, list):
        raise RuntimeError("predictions.json is not a list")
    if not isinstance(bets, list):
        raise RuntimeError("bets.json is not a list")

    pipeline = health.get("pipeline") or {}
    rejection_records = health.get("funnel_rejections") or []
    if not isinstance(rejection_records, list):
        raise RuntimeError("funnel_rejections is not a list")

    reason_counts = Counter(
        str(item.get("reason"))
        for item in rejection_records
        if isinstance(item, dict) and item.get("reason")
    )
    selected_predictions = {
        str(item.get("id"))
        for item in predictions
        if isinstance(item, dict) and item.get("selected") is True and item.get("id")
    }
    persisted_prediction_ids = {
        str(item.get("prediction_id"))
        for item in bets
        if isinstance(item, dict) and item.get("prediction_id")
    }
    selected_not_persisted = sorted(selected_predictions - persisted_prediction_ids)

    funnel = health.get("funnel") or {}
    return {
        "schema_version": 1,
        "timestamp": health.get("timestamp"),
        "generation_status": health.get("status"),
        "observation_only": health.get("observation_only", True),
        "funnel": funnel,
        "pipeline": {
            "fixtures_discovered": int(pipeline.get("fixtures_discovered", 0)),
            "fixtures_eligible": int(pipeline.get("fixtures_eligible", 0)),
            "fixtures_modelled": int(pipeline.get("fixtures_modelled", 0)),
            "predictions_generated": int(pipeline.get("predictions_generated", 0)),
            "candidates_qualified": int(pipeline.get("candidates_qualified", 0)),
            "risk_checks": int(pipeline.get("risk_checks", 0)),
            "selections_produced": int(pipeline.get("selections_produced", 0)),
            "duplicate_rejections": int(pipeline.get("duplicate_rejections", 0)),
            "persistence_failures": int(pipeline.get("persistence_failures", 0)),
        },
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "selected_prediction_count_from_artifact": len(selected_predictions),
        "persisted_prediction_count_from_artifact": len(persisted_prediction_ids),
        "selected_not_persisted": selected_not_persisted,
        "reconciliation": {
            "selected_predictions_persisted": not selected_not_persisted,
            "reason_records_auditable": all(
                isinstance(item, dict)
                and item.get("stage")
                and item.get("reason")
                for item in rejection_records
            ),
            "monotonic_fixture_stages": (
                int(funnel.get("discovered", 0))
                >= int(funnel.get("eligible", 0))
                >= int(funnel.get("modelled", 0))
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit persisted QuantBet decision funnel")
    parser.add_argument("--output", default="decision_funnel_audit.json")
    args = parser.parse_args()
    audit = build_audit()
    output = ROOT / args.output
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all(audit["reconciliation"].values()):
        raise SystemExit("Decision funnel audit failed reconciliation")
    print(json.dumps(audit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
