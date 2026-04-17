# Dashboard (Phase E MVP)

Dashboard provides an interactive analysis panel for:

- baseline / torch / nsys comparison
- offline / PD scenario slices
- prefill / decode / unknown phase slices

Core plots:

- overhead curve
- stage time stacked bars
- pareto (throughput vs latency)

## Start

Install runtime dependencies first:

```bash
pip install streamlit plotly
```

Then start dashboard:

```bash
streamlit run src/dashboard/app.py -- --runs-root experiments/runs
```

You can also point to another runs root:

```bash
streamlit run src/dashboard/app.py -- --runs-root step_reports/pipeline_runs
```

## Data Dependencies

For each run folder, dashboard consumes:

- `manifests/run_manifest.json`
- `calibration/calibration_dataset_v1.csv`
- optional `calibration/evaluation_report.json`
- optional `regression/regression_compare.json`
- optional `regression/threshold_check.json`

## Tests

```bash
python -m unittest tests.unit.dashboard.test_data_loader tests.unit.dashboard.test_charts tests.integration.test_dashboard_data_smoke -v
```
