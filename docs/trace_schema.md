# Trace Schema (Phase B MVP)

TraceKit normalizes PyTorch profiler traces and nsys exported events into one event table.
It is manifest-aware: when `run_manifest.json` is present, TraceKit uses case metadata to recover `scenario/mode/rank` more accurately.

## Input

- PyTorch trace files: `*.trace.json` / `*.trace.json.gz`
- nsys exported files:
  - JSON / CSV containing event rows (`name`, `start_us`, `duration_us`, etc.)
  - SQLite (`.sqlite` / `.sqlite3`) containing activity tables with start/end or duration columns
- nsys report files:
  - `.nsys-rep` (TraceKit will auto materialize to SQLite via `nsys export`, and fallback to CSV via `nsys stats` if needed)

## Unified Event Fields

- `run_id`
- `scenario`: `offline|pd|unknown`
- `mode`: `baseline|torch|nsys|torch_prefill|torch_decode|unknown`
- `source`: `torch|nsys`
- `rank`
- `device`
- `stream_id`
- `phase`: `prefill|decode|unknown`
- `op_name`
- `category`: `compute|communication|memory|scheduler|idle|other`
- `ts_us`
- `dur_us`
- `corr_id` (nullable)
- `case_id`
- `extras` (source-specific aux fields)

## Aggregate Outputs

TraceKit CLI writes:

- `normalized_events.jsonl`
- `phase_metrics.json`
- `op_metrics_top.json`
- `queue_wait_metrics.json`
- `summary.json`

`phase_metrics.json` now includes KV transfer related fields:

- `kv_cache_transfer_time_us`
- `kv_cache_transfer_events`
- `kv_cache_transfer_ratio`

`summary.json` now includes:

- `kv_cache_transfer_total_time_us`
- `kv_cache_transfer_total_events`
- `kv_cache_transfer_ratio`

## CLI

```bash
python -m src.tracekit.cli \
  --input experiments/runs/<run_id> \
  --output experiments/runs/<run_id>/normalized \
  --nsys-bin nsys
```

Disable `.nsys-rep` auto materialization:

```bash
python -m src.tracekit.cli \
  --input experiments/runs/<run_id> \
  --output experiments/runs/<run_id>/normalized \
  --disable-nsys-rep-export
```

## Test

```bash
python -m unittest tests.unit.tracekit.test_normalizer tests.unit.tracekit.test_context_resolver tests.unit.tracekit.test_nsys_reader tests.unit.tracekit.test_nsys_rep_adapter tests.integration.test_tracekit_smoke -v
```

Real sample replay smoke (optional):

```bash
RUN_REAL_TRACEKIT_SMOKE=1 python -m unittest tests.integration.test_tracekit_smoke -v
```
