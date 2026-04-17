# Regression Baseline System (Phase D)

Regression module provides:

- baseline snapshot creation
- run-vs-baseline comparison
- threshold gate (machine-readable, CI-friendly)
- markdown regression report

## Baseline Create

```bash
python -m src.regression.cli baseline create \
  --run-root experiments/runs/<run_id> \
  --baseline-id offline_pd_ref_v1 \
  --baselines-root experiments/baselines
```

## Compare + Report + Threshold Check

```bash
python -m src.regression.cli compare \
  --run-root experiments/runs/<new_run_id> \
  --baseline-id offline_pd_ref_v1 \
  --baselines-root experiments/baselines \
  --thresholds experiments/thresholds/default_thresholds.yaml \
  --fail-on-threshold
```

Outputs (default `<run_root>/regression`):

- `regression_compare.json`
- `threshold_check.json`
- `regression_report.md`

## Check Only

```bash
python -m src.regression.cli check \
  --compare-json experiments/runs/<new_run_id>/regression/regression_compare.json \
  --thresholds experiments/thresholds/default_thresholds.yaml \
  --fail-on-threshold
```

## Threshold Rules (Default)

File: `experiments/thresholds/default_thresholds.yaml`

- `max_runner_duration_regression_pct`
- `min_trace_coverage_ratio`
- `min_gpu_util_ratio_vs_baseline`
- `allow_new_groups`
- `allow_missing_current_groups`
- `require_metric_values`
- `apply_only_profile_modes`

## Tests

```bash
python -m unittest tests.unit.regression.test_baseline_store tests.unit.regression.test_comparator_thresholds tests.integration.test_regression_smoke -v
```

