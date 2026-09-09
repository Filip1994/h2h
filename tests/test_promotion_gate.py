from tools.validate_promotion_package import validate


def test_valid_promotion_package_passes() -> None:
    package = {
        "dataset_id": "ds-1",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "point_in_time_safe": True,
        "code_sha": "abc",
        "config_hash": "cfg",
        "model_version": "v2",
        "baseline": {"brier": 0.20, "log_loss": 0.60},
        "proposed": {"brier": 0.19, "log_loss": 0.57},
        "ablation_complete": True,
        "leakage_review": True,
        "selection_bias_review": True,
        "stability_review": True,
        "confidence_intervals": {"brier": [0.18, 0.20]},
        "sample_size": 1000,
        "rollback_version": "prod-v1",
        "production_pr": "#123",
    }
    assert validate(package) == []


def test_missing_leakage_review_blocks_promotion() -> None:
    package = {
        "dataset_id": "ds-1",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "point_in_time_safe": True,
        "code_sha": "abc",
        "config_hash": "cfg",
        "model_version": "v2",
        "baseline": {"brier": 0.20, "log_loss": 0.60},
        "proposed": {"brier": 0.19, "log_loss": 0.57},
        "ablation_complete": True,
        "leakage_review": False,
        "selection_bias_review": True,
        "stability_review": True,
        "confidence_intervals": {},
        "sample_size": 1000,
        "rollback_version": "prod-v1",
        "production_pr": "#123",
    }
    assert "leakage_review must be true" in validate(package)
