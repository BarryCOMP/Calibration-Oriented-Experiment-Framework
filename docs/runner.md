# Runner (Phase A MVP)

This module provides a configuration-driven experiment runner skeleton.

Current status:
- YAML config loading and validation
- Matrix expansion into executable cases
- Sequential orchestration (single-process case scheduling)
- Offline executor (baseline / torch / nsys)
- PD executor (baseline / torch_prefill / torch_decode / nsys_prefill / nsys_decode / nsys)
- Retry and manifest writing
- Dry-run support

## Entrypoint

```bash
python -m src.runner.cli --config experiments/configs/offline_baseline.yaml --dry-run
```

## Minimal real run

```bash
python -m src.runner.cli --config experiments/configs/offline_baseline.yaml
```

## Continue-on-error run

```bash
python -m src.runner.cli \
  --config experiments/configs/offline_baseline.yaml \
  --continue-on-error
```

## Output layout

```text
experiments/runs/<run_id>/
  manifests/run_manifest.json
  cases/<case_id>/
    logs/
    results/
    traces/
```

## Notes

- `max_parallel_cases` is recorded but not yet enforced in Phase A (execution is sequential).
- Phase A focuses on execution scaffolding and artifact management, not full optimization.
- Failed cases include log-tail diagnostics in manifest fields:
  - `error_log_tail`, `error_summary`
  - `extra_log_tails`, `extra_log_summaries` (e.g. PD side logs)
- Fair PD comparison recommendation:
  - Use `torch_prefill` vs `nsys_prefill`, and `torch_decode` vs `nsys_decode`
  - Keep `mode=nsys` only for system-level "both servers profiled together" runs
- Auto-expansion in PD:
  - If config uses `mode=torch`, runner expands to `torch_prefill` + `torch_decode`
  - If config uses `mode=nsys`, runner expands to:
    - `nsys_prefill` + `nsys_decode` (default), or
    - `nsys` when `pd_nsys_compare_mode=both`

## Tests

Unit tests (no GPU/runtime required):

```bash
python -m unittest tests.unit.runner.test_continue_on_error tests.unit.runner.test_diagnostics -v
```

Real small-load smoke (requires runtime + model + GPU):

```bash
RUN_REAL_SMOKE=1 python -m unittest tests.integration.test_runner_smoke -v
```
