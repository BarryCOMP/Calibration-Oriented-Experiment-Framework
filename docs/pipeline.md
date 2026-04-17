# End-to-End Pipeline (M4)

One command chain:

`runner -> tracekit -> calibration`  
Optional extension: `-> regression`

## CLI

```bash
python -m src.pipeline.cli \
  --config experiments/configs/pd_profile_compare.yaml
```

## Common Options

- `--runner-dry-run`: run runner in dry-run mode (for quick smoke)
- `--continue-on-error`: continue runner cases after failure
- `--output-root`: override runner output root
- `--run-name`: override runner run name
- `--trace-top-n`: tracekit top-N op metrics
- `--nsys-bin`: nsys binary path
- `--disable-nsys-rep-export`: disable auto materialization for `.nsys-rep`
- `--calibration-output`: custom calibration output directory
- `--regression-baseline-id`: enable regression compare/check stage
- `--regression-baselines-root`: baseline store root (default `experiments/baselines`)
- `--regression-thresholds`: threshold yaml/json path
- `--fail-on-regression-threshold`: return non-zero when threshold gate fails

## With Regression

```bash
python -m src.pipeline.cli \
  --config experiments/configs/pd_profile_compare.yaml \
  --regression-baseline-id offline_pd_ref_v1 \
  --regression-baselines-root experiments/baselines \
  --regression-thresholds experiments/thresholds/default_thresholds.yaml \
  --fail-on-regression-threshold
```

## Output

- runner artifacts: `experiments/runs/<run_id>/...`
- tracekit artifacts: `experiments/runs/<run_id>/normalized/...`
- calibration artifacts: `experiments/runs/<run_id>/calibration/...`
- regression artifacts (when enabled): `experiments/runs/<run_id>/regression/...`
- pipeline summary: `.../calibration/pipeline_summary.json`

PD compare note:
- For fair profiler-overhead comparison, prefer PD modes:
  - `torch_prefill` vs `nsys_prefill`
  - `torch_decode` vs `nsys_decode`
- `mode=nsys` profiles both prefill/decode servers together and is not directly
  comparable to one-side torch profiling.

## Test

```bash
python -m unittest tests.integration.test_pipeline_e2e -v
```

## Full Round (Phase A -> E)

This command runs one full round where all later phases consume artifacts generated in the same round:

```bash
python -m src.pipeline.phase_a_to_e \
  --config experiments/configs/pd_profile_compare.yaml \
  --work-root step_reports/phase_a_to_e_rounds \
  --runner-dry-run
```

Or use the helper script:

```bash
bash scripts/run_phase_a_to_e_once.sh \
  experiments/configs/pd_profile_compare.yaml \
  step_reports/phase_a_to_e_rounds
```

Round output includes:

- `<round_root>/runs/<round>_baseline_*/...` (A/B/C baseline run)
- `<round_root>/runs/<round>_current_*/...` (A/B/C/D current run)
- `<round_root>/dashboard_data_summary.json` (E data check)
- `<round_root>/round_summary.json` (full chain summary)
