# Calibration Dataset (Phase C MVP)

Calibration module consumes runner + tracekit artifacts and produces:

- versioned dataset (`jsonl` + `csv`)
- metadata (`metadata.json`)
- validation report (`validation_report.json`)
- evaluation reports (`evaluation_report.json` + `evaluation_report.md`)

## Input

- run root: `experiments/runs/<run_id>`
- required:
  - `manifests/run_manifest.json`
  - `normalized/normalized_events.jsonl` (from TraceKit)

## CLI

```bash
python -m src.calibration.cli \
  --run-root experiments/runs/<run_id> \
  --output experiments/runs/<run_id>/calibration
```

Optional: auto-run TraceKit when normalized events are missing:

```bash
python -m src.calibration.cli \
  --run-root experiments/runs/<run_id> \
  --output experiments/runs/<run_id>/calibration \
  --auto-tracekit \
  --nsys-bin nsys
```

## Dataset Row (MVP)

- run/case info: `run_id`, `case_id`, `scenario`, `mode`, `status`, `attempt`
- phase: `phase`
- runner metric: `runner_duration_sec`
- trace metrics:
  - `num_events`
  - `total_trace_time_us`
  - `compute_time_us`, `comm_time_us`, `memory_time_us`, `scheduler_time_us`, `idle_time_us`, `other_time_us`
  - `trace_span_us`
  - `gpu_util_proxy`
  - `trace_coverage`

## Test

```bash
python -m unittest tests.unit.calibration.test_dataset_builder tests.unit.calibration.test_validators tests.unit.calibration.test_evaluate tests.integration.test_calibration_smoke -v
```

