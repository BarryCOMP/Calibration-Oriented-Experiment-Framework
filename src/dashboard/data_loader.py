from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import find_run_roots, safe_read_csv, safe_read_json, to_float


def discover_runs(runs_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_root in find_run_roots(runs_root):
        manifest_path = run_root / "manifests" / "run_manifest.json"
        try:
            manifest = safe_read_json(manifest_path)
        except Exception:
            continue
        rows.append(
            {
                "run_id": str(manifest.get("run_id", run_root.name)),
                "run_root": str(run_root),
                "created_at_epoch": to_float(manifest.get("created_at_epoch")),
                "dry_run": bool(manifest.get("dry_run", False)),
                "total_cases": int(manifest.get("total_cases", 0) or 0),
                "executed_cases": int(manifest.get("executed_cases", 0) or 0),
                "has_failure": bool(manifest.get("has_failure", False)),
                "status_counts": manifest.get("status_counts", {}),
            }
        )
    return rows


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return safe_read_json(path)
    except Exception:
        return None


def _extract_result_metrics_from_path(result_path: str | None) -> dict[str, float | None]:
    # Heuristic extraction from benchmark result jsonl/json.
    # Keep this tolerant because different benchmark tools may emit different fields.
    if not result_path:
        return {"throughput": None, "latency_ms": None}
    p = Path(result_path)
    if not p.exists():
        return {"throughput": None, "latency_ms": None}

    rows: list[dict[str, Any]] = []
    try:
        if p.suffix.lower() == ".jsonl":
            from .utils import safe_read_jsonl

            rows = safe_read_jsonl(p)
        elif p.suffix.lower() == ".json":
            d = safe_read_json(p)
            if isinstance(d, dict):
                rows = [d]
    except Exception:
        rows = []

    # candidate field names
    throughput_keys = [
        "request_throughput",
        "throughput",
        "output_throughput",
        "tokens_per_second",
        "tps",
    ]
    latency_keys = [
        "latency_ms",
        "mean_latency_ms",
        "avg_latency_ms",
        "p50_latency_ms",
        "ttft_ms",
        "itl_ms",
    ]

    def pick(keys: list[str]) -> float | None:
        for r in rows:
            for k in keys:
                if k in r:
                    v = to_float(r.get(k))
                    if v is not None:
                        return v
        return None

    return {
        "throughput": pick(throughput_keys),
        "latency_ms": pick(latency_keys),
    }


def load_run_bundle(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    manifest_path = run_root / "manifests" / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"run manifest not found: {manifest_path}")
    manifest = safe_read_json(manifest_path)

    calibration_dir = run_root / "calibration"
    regression_dir = run_root / "regression"
    normalized_dir = run_root / "normalized"

    calibration_summary = _load_optional_json(calibration_dir / "summary.json")
    calibration_eval = _load_optional_json(calibration_dir / "evaluation_report.json")
    calibration_validation = _load_optional_json(calibration_dir / "validation_report.json")
    calibration_rows = safe_read_csv(calibration_dir / "calibration_dataset_v1.csv") if (calibration_dir / "calibration_dataset_v1.csv").exists() else []

    # enrich case-level throughput/latency with heuristics from result files
    for row in calibration_rows:
        result_metrics = _extract_result_metrics_from_path(str(row.get("result_path") or ""))
        if result_metrics["throughput"] is None:
            # fallback proxy: events/sec
            num_events = to_float(row.get("num_events"))
            dur = to_float(row.get("runner_duration_sec"))
            if num_events is not None and dur is not None and dur > 0:
                result_metrics["throughput"] = num_events / dur
        if result_metrics["latency_ms"] is None:
            # fallback proxy: runner duration in ms
            dur = to_float(row.get("runner_duration_sec"))
            if dur is not None:
                result_metrics["latency_ms"] = dur * 1000.0
        row["throughput_metric"] = result_metrics["throughput"]
        row["latency_metric_ms"] = result_metrics["latency_ms"]

    regression_compare = _load_optional_json(regression_dir / "regression_compare.json")
    threshold_check = _load_optional_json(regression_dir / "threshold_check.json")
    tracekit_summary = _load_optional_json(normalized_dir / "summary.json")

    return {
        "run_root": str(run_root),
        "manifest": manifest,
        "calibration_summary": calibration_summary,
        "calibration_eval": calibration_eval,
        "calibration_validation": calibration_validation,
        "calibration_rows": calibration_rows,
        "regression_compare": regression_compare,
        "threshold_check": threshold_check,
        "tracekit_summary": tracekit_summary,
    }

