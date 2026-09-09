from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = {
    "dataset_id",
    "period_start",
    "period_end",
    "point_in_time_safe",
    "code_sha",
    "config_hash",
    "model_version",
    "baseline",
    "proposed",
    "ablation_complete",
    "leakage_review",
    "selection_bias_review",
    "stability_review",
    "confidence_intervals",
    "sample_size",
    "rollback_version",
    "production_pr",
}


def validate(package: dict) -> list[str]:
    errors = sorted(REQUIRED - package.keys())
    if package.get("point_in_time_safe") is not True:
        errors.append("point_in_time_safe must be true")
    for review in (
        "ablation_complete",
        "leakage_review",
        "selection_bias_review",
        "stability_review",
    ):
        if package.get(review) is not True:
            errors.append(f"{review} must be true")
    if int(package.get("sample_size", 0)) <= 0:
        errors.append("sample_size must be positive")
    for side in ("baseline", "proposed"):
        metrics = package.get(side) or {}
        for metric in ("brier", "log_loss"):
            if metric not in metrics:
                errors.append(f"{side}.{metric} missing")
    if not package.get("rollback_version"):
        errors.append("rollback_version missing")
    if not package.get("production_pr"):
        errors.append("production_pr missing")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8"))
    errors = validate(package)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PROMOTION_PACKAGE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
