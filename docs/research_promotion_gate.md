# Football Research → Production Promotion Gate

No Football model, feature, calibration, timing, threshold or market-selection change may affect Production merely because research code is merged.

## Required artifact lifecycle

`Research → isolated backtest → walk-forward OOS → baseline comparison → ablation → stability → promotion decision → Production PR`

A promotion package must contain machine-readable metadata for the exact dataset, point-in-time feature cutoff, code/config/model versions, baseline and proposed metrics, segmentation, leakage review, selection-bias review, confidence intervals, and rollback plan.

## Hard gates

1. **Dataset identity:** immutable dataset ID, exact period, and point-in-time cutoff rules.
2. **No leakage:** every feature has an availability timestamp no later than the prediction timestamp.
3. **OOS discipline:** final evaluation data is not used to tune thresholds or select the winning variant.
4. **Baseline comparison:** current Production baseline is evaluated on the same unseen observations.
5. **Ablation:** incremental value is measured against the baseline, not only against a weak alternative.
6. **Stability:** results are segmented by relevant market/league/odds/time buckets where sample permits.
7. **Uncertainty:** small samples are marked inconclusive; confidence intervals accompany applicable metrics.
8. **Rollback:** exact Production version and rollback target are named before promotion.
9. **Explicit Production change:** a separate Production PR is required. Research artifacts alone never alter Production configuration.

## Required promotion manifest

The validator expects a JSON document with:

- `dataset_id`, `period_start`, `period_end`, `point_in_time_safe`;
- `code_sha`, `config_hash`, `model_version`;
- `baseline` and `proposed` metric objects containing Brier/log loss and relevant CLV/ROI metrics;
- `ablation_complete`, `leakage_review`, `selection_bias_review`, `stability_review`;
- `confidence_intervals`;
- `sample_size`;
- `rollback_version`;
- `production_pr`.

A package can be valid and still be **INCONCLUSIVE**: statistical evidence must decide whether the proposed change is superior. The gate only prevents unsupported promotion; it does not manufacture significance.

## Production isolation

Research modules must live under research/diagnostics paths or explicit experiment namespaces. Production imports must not resolve experiment variants implicitly. Any promotion changes the Production dependency/configuration through a reviewed PR and updates the immutable decision packet strategy/version metadata.
