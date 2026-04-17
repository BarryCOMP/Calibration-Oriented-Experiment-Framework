from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "run_id",
    "case_id",
    "scenario",
    "mode",
    "phase",
    "status",
    "num_events",
    "total_trace_time_us",
    "trace_coverage",
]


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def validate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_field_issues = 0
    negative_value_issues = 0
    bad_ratio_issues = 0
    status_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}

    for row in rows:
        for k in REQUIRED_FIELDS:
            if k not in row:
                missing_field_issues += 1

        for k in [
            "num_events",
            "total_trace_time_us",
            "compute_time_us",
            "comm_time_us",
            "memory_time_us",
            "scheduler_time_us",
            "idle_time_us",
            "other_time_us",
            "trace_span_us",
        ]:
            if _as_float(row.get(k, 0.0)) < 0:
                negative_value_issues += 1

        for k in ["trace_coverage", "gpu_util_proxy"]:
            v = _as_float(row.get(k, 0.0))
            if v < 0.0 or v > 1.0 + 1e-9:
                bad_ratio_issues += 1

        st = str(row.get("status", "unknown"))
        ph = str(row.get("phase", "unknown"))
        status_counts[st] = status_counts.get(st, 0) + 1
        phase_counts[ph] = phase_counts.get(ph, 0) + 1

    total_rows = len(rows)
    traced_rows = sum(1 for r in rows if _as_int(r.get("num_events", 0)) > 0)
    unknown_case_rows = sum(1 for r in rows if str(r.get("status", "")) == "unknown")

    report = {
        "rows_total": total_rows,
        "rows_with_trace": traced_rows,
        "trace_row_ratio": (traced_rows / total_rows) if total_rows > 0 else 0.0,
        "rows_unknown_case": unknown_case_rows,
        "status_counts": status_counts,
        "phase_counts": phase_counts,
        "issues": {
            "missing_field_issues": missing_field_issues,
            "negative_value_issues": negative_value_issues,
            "bad_ratio_issues": bad_ratio_issues,
            "total_issues": missing_field_issues + negative_value_issues + bad_ratio_issues,
        },
        "is_valid": (missing_field_issues + negative_value_issues + bad_ratio_issues) == 0,
    }
    return report


def validate_dataset_file(dataset_jsonl: Path, output_path: Path | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with dataset_jsonl.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                r = json.loads(text)
            except Exception:
                continue
            if isinstance(r, dict):
                rows.append(r)
    report = validate_rows(rows)
    if output_path is not None:
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

