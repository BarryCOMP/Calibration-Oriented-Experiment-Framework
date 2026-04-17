from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .baseline_store import get_baseline_entry, resolve_calibration_dir
from .schema import GroupKey


TRACKED_METRICS = [
    "avg_runner_duration_sec",
    "avg_trace_time_us",
    "avg_gpu_util_proxy",
    "trace_coverage_ratio",
]


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict json: {path}")
    return data


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _metric_diff(b: Any, c: Any) -> dict[str, Any]:
    bv = _to_float(b)
    cv = _to_float(c)
    if bv is None and cv is None:
        return {
            "baseline": None,
            "current": None,
            "abs_delta": None,
            "pct_delta": None,
            "ratio_to_baseline": None,
        }
    if bv is None or cv is None:
        return {
            "baseline": bv,
            "current": cv,
            "abs_delta": None,
            "pct_delta": None,
            "ratio_to_baseline": None,
        }
    abs_delta = cv - bv
    pct_delta = (abs_delta / bv * 100.0) if bv != 0 else None
    ratio = (cv / bv) if bv != 0 else None
    return {
        "baseline": bv,
        "current": cv,
        "abs_delta": abs_delta,
        "pct_delta": pct_delta,
        "ratio_to_baseline": ratio,
    }


def _groups_to_map(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for g in groups:
        if not isinstance(g, dict):
            continue
        out[GroupKey.from_row(g).to_string()] = g
    return out


def load_current_groups(run_root: Path, calibration_dir: Path | None = None) -> dict[str, Any]:
    cal_dir = resolve_calibration_dir(run_root.resolve(), calibration_dir)
    evaluation_path = cal_dir / "evaluation_report.json"
    if not evaluation_path.exists():
        raise FileNotFoundError(f"Missing evaluation report: {evaluation_path}")
    evaluation = _read_json(evaluation_path)
    groups = evaluation.get("groups", [])
    if not isinstance(groups, list):
        groups = []
    return {
        "calibration_dir": str(cal_dir),
        "evaluation_path": str(evaluation_path),
        "evaluation": evaluation,
        "groups": groups,
        "groups_map": _groups_to_map(groups),
    }


def load_baseline_groups(baselines_root: Path, baseline_id: str) -> dict[str, Any]:
    entry = get_baseline_entry(baselines_root.resolve(), baseline_id)
    baseline_dir = Path(str(entry["path"])).resolve()
    metrics_path = baseline_dir / "metrics_summary.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"Baseline metrics missing: {metrics_path}")
    metrics = _read_json(metrics_path)
    groups = metrics.get("groups", [])
    if not isinstance(groups, list):
        groups = []
    groups_map = metrics.get("groups_map", {})
    if not isinstance(groups_map, dict) or not groups_map:
        groups_map = _groups_to_map(groups)
    return {
        "entry": entry,
        "baseline_dir": str(baseline_dir),
        "metrics_path": str(metrics_path),
        "groups": groups,
        "groups_map": groups_map,
    }


def build_compare_report(
    run_root: Path,
    baselines_root: Path,
    baseline_id: str,
    calibration_dir: Path | None = None,
) -> dict[str, Any]:
    cur = load_current_groups(run_root, calibration_dir)
    base = load_baseline_groups(baselines_root, baseline_id)
    cur_map: dict[str, Any] = cur["groups_map"]
    base_map: dict[str, Any] = base["groups_map"]

    all_keys = sorted(set(cur_map.keys()) | set(base_map.keys()))
    rows: list[dict[str, Any]] = []
    matched = 0
    missing_current = 0
    new_groups = 0

    for key in all_keys:
        b = base_map.get(key)
        c = cur_map.get(key)
        if b is not None and c is not None:
            status = "matched"
            matched += 1
        elif b is not None and c is None:
            status = "missing_current"
            missing_current += 1
        else:
            status = "new_group"
            new_groups += 1

        ref = c if c is not None else b if b is not None else {}
        gk = GroupKey.from_row(ref)
        diff: dict[str, Any] = {}
        for m in TRACKED_METRICS:
            diff[m] = _metric_diff(
                b.get(m) if isinstance(b, dict) else None,
                c.get(m) if isinstance(c, dict) else None,
            )

        rows.append(
            {
                "key": key,
                "scenario": gk.scenario,
                "mode": gk.mode,
                "phase": gk.phase,
                "status": status,
                "baseline": b,
                "current": c,
                "diff": diff,
            }
        )

    report = {
        "version": "regression_compare_v1",
        "created_at_epoch": time.time(),
        "baseline": {
            "baseline_id": baseline_id,
            "baseline_dir": base["baseline_dir"],
            "metrics_path": base["metrics_path"],
            "run_id": base["entry"].get("run_id"),
        },
        "current": {
            "run_root": str(run_root.resolve()),
            "calibration_dir": cur["calibration_dir"],
            "evaluation_path": cur["evaluation_path"],
        },
        "summary": {
            "total_groups": len(all_keys),
            "matched_groups": matched,
            "missing_current_groups": missing_current,
            "new_groups": new_groups,
        },
        "rows": rows,
    }
    return report

