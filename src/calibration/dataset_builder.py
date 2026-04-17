from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .versioning import build_metadata


CATEGORY_FIELDS = {
    "compute": "compute_time_us",
    "communication": "comm_time_us",
    "memory": "memory_time_us",
    "scheduler": "scheduler_time_us",
    "idle": "idle_time_us",
    "other": "other_time_us",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def load_run_manifest(run_root: Path) -> dict[str, Any]:
    direct = run_root / "manifests" / "run_manifest.json"
    if direct.exists():
        data = _read_json(direct)
        if isinstance(data, dict):
            return data
    candidates = sorted(run_root.rglob("run_manifest.json"))
    for p in candidates:
        data = _read_json(p)
        if isinstance(data, dict):
            return data
    raise FileNotFoundError(f"run_manifest.json not found under {run_root}")


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception:
                continue
            if isinstance(row, dict):
                yield row


def _default_agg() -> dict[str, Any]:
    out = {
        "num_events": 0,
        "total_trace_time_us": 0.0,
        "compute_time_us": 0.0,
        "comm_time_us": 0.0,
        "memory_time_us": 0.0,
        "scheduler_time_us": 0.0,
        "idle_time_us": 0.0,
        "other_time_us": 0.0,
        "first_ts_us": None,
        "last_end_us": None,
    }
    return out


def aggregate_events_by_case_phase(normalized_events_jsonl: Path) -> dict[tuple[str, str], dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for e in _iter_jsonl(normalized_events_jsonl):
        case_id = str(e.get("case_id", "unknown"))
        phase = str(e.get("phase", "unknown"))
        key = (case_id, phase)
        agg = buckets.get(key)
        if agg is None:
            agg = _default_agg()
            buckets[key] = agg

        dur = float(e.get("dur_us", 0.0) or 0.0)
        ts = float(e.get("ts_us", 0.0) or 0.0)
        end = ts + max(0.0, dur)
        agg["num_events"] += 1
        agg["total_trace_time_us"] += max(0.0, dur)
        if agg["first_ts_us"] is None or ts < float(agg["first_ts_us"]):
            agg["first_ts_us"] = ts
        if agg["last_end_us"] is None or end > float(agg["last_end_us"]):
            agg["last_end_us"] = end

        category = str(e.get("category", "other"))
        f = CATEGORY_FIELDS.get(category, "other_time_us")
        agg[f] += max(0.0, dur)
    return buckets


def _build_row_base(run_id: str, case: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "case_id": str(case.get("case_id", "unknown")),
        "scenario": str(case.get("scenario", "unknown")),
        "mode": str(case.get("mode", "unknown")),
        "status": str(case.get("status", "unknown")),
        "attempt": int(case.get("attempt", 0) or 0),
        "runner_duration_sec": float(case.get("duration_sec", 0.0) or 0.0),
        "trace_path": case.get("trace_path"),
        "result_path": case.get("result_path"),
        "log_path": case.get("log_path"),
        "error": case.get("error"),
        "error_summary": case.get("error_summary"),
    }


def build_dataset_rows(
    manifest: dict[str, Any],
    normalized_events_jsonl: Path,
) -> list[dict[str, Any]]:
    run_id = str(manifest.get("run_id", "unknown"))
    cases_raw = manifest.get("cases", [])
    cases = [c for c in cases_raw if isinstance(c, dict)]
    events_by_case_phase = aggregate_events_by_case_phase(normalized_events_jsonl)

    known_case_ids = {str(c.get("case_id", "unknown")) for c in cases}
    rows: list[dict[str, Any]] = []

    for case in cases:
        case_id = str(case.get("case_id", "unknown"))
        base = _build_row_base(run_id, case)
        phase_keys = [k for k in events_by_case_phase.keys() if k[0] == case_id]
        if not phase_keys:
            row = dict(base)
            row.update(
                {
                    "phase": "unknown",
                    "num_events": 0,
                    "total_trace_time_us": 0.0,
                    "compute_time_us": 0.0,
                    "comm_time_us": 0.0,
                    "memory_time_us": 0.0,
                    "scheduler_time_us": 0.0,
                    "idle_time_us": 0.0,
                    "other_time_us": 0.0,
                    "trace_span_us": 0.0,
                    "gpu_util_proxy": 0.0,
                    "trace_coverage": 0.0,
                }
            )
            rows.append(row)
            continue

        for key in sorted(phase_keys):
            agg = events_by_case_phase[key]
            total = float(agg["total_trace_time_us"])
            active = float(agg["compute_time_us"]) + float(agg["comm_time_us"])
            span = 0.0
            if agg["first_ts_us"] is not None and agg["last_end_us"] is not None:
                span = max(0.0, float(agg["last_end_us"]) - float(agg["first_ts_us"]))
            row = dict(base)
            row.update(
                {
                    "phase": key[1],
                    "num_events": int(agg["num_events"]),
                    "total_trace_time_us": total,
                    "compute_time_us": float(agg["compute_time_us"]),
                    "comm_time_us": float(agg["comm_time_us"]),
                    "memory_time_us": float(agg["memory_time_us"]),
                    "scheduler_time_us": float(agg["scheduler_time_us"]),
                    "idle_time_us": float(agg["idle_time_us"]),
                    "other_time_us": float(agg["other_time_us"]),
                    "trace_span_us": span,
                    "gpu_util_proxy": (active / total) if total > 0 else 0.0,
                    "trace_coverage": 1.0 if total > 0 else 0.0,
                }
            )
            rows.append(row)

    # keep unmatched events as extra rows for debugging/coverage
    for (case_id, phase), agg in sorted(events_by_case_phase.items()):
        if case_id in known_case_ids:
            continue
        total = float(agg["total_trace_time_us"])
        active = float(agg["compute_time_us"]) + float(agg["comm_time_us"])
        rows.append(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scenario": "unknown",
                "mode": "unknown",
                "status": "unknown",
                "attempt": 0,
                "runner_duration_sec": 0.0,
                "trace_path": None,
                "result_path": None,
                "log_path": None,
                "error": None,
                "error_summary": None,
                "phase": phase,
                "num_events": int(agg["num_events"]),
                "total_trace_time_us": total,
                "compute_time_us": float(agg["compute_time_us"]),
                "comm_time_us": float(agg["comm_time_us"]),
                "memory_time_us": float(agg["memory_time_us"]),
                "scheduler_time_us": float(agg["scheduler_time_us"]),
                "idle_time_us": float(agg["idle_time_us"]),
                "other_time_us": float(agg["other_time_us"]),
                "trace_span_us": max(
                    0.0,
                    float(agg["last_end_us"] or 0.0) - float(agg["first_ts_us"] or 0.0),
                ),
                "gpu_util_proxy": (active / total) if total > 0 else 0.0,
                "trace_coverage": 1.0 if total > 0 else 0.0,
            }
        )

    rows.sort(key=lambda r: (str(r["case_id"]), str(r["phase"])))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def build_calibration_dataset(
    run_root: Path,
    output_dir: Path,
    normalized_dir: Path | None = None,
    dataset_version: str = "v1",
) -> dict[str, Any]:
    run_root = run_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_run_manifest(run_root)
    if normalized_dir is None:
        normalized_dir = run_root / "normalized"
    normalized_events = normalized_dir / "normalized_events.jsonl"
    if not normalized_events.exists():
        raise FileNotFoundError(
            f"Normalized events not found: {normalized_events}. "
            "Run TraceKit first: python -m src.tracekit.cli --input <run_root> --output <run_root>/normalized"
        )

    rows = build_dataset_rows(manifest=manifest, normalized_events_jsonl=normalized_events)

    dataset_jsonl = output_dir / f"calibration_dataset_{dataset_version}.jsonl"
    dataset_csv = output_dir / f"calibration_dataset_{dataset_version}.csv"
    metadata_path = output_dir / "metadata.json"

    _write_jsonl(dataset_jsonl, rows)
    _write_csv(dataset_csv, rows)
    metadata = build_metadata(run_root, manifest, dataset_version=dataset_version, dataset_rows=len(rows))
    _write_json(metadata_path, metadata)

    return {
        "dataset_rows": len(rows),
        "dataset_jsonl": str(dataset_jsonl),
        "dataset_csv": str(dataset_csv),
        "metadata": str(metadata_path),
        "run_id": str(manifest.get("run_id", "unknown")),
        "normalized_events": str(normalized_events),
    }

