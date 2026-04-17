from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLDS = {
    "version": "v1",
    "rules": {
        "max_runner_duration_regression_pct": 20.0,
        "min_trace_coverage_ratio": 0.0,
        "min_gpu_util_ratio_vs_baseline": 0.0,
        "allow_new_groups": True,
        "allow_missing_current_groups": False,
        "require_metric_values": False,
        "apply_only_profile_modes": False,
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict json: {path}")
    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "PyYAML is required to load threshold yaml. Install with: pip install pyyaml"
        ) from e
    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict yaml: {path}")
    return data


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        return DEFAULT_THRESHOLDS
    if not path.exists():
        raise FileNotFoundError(f"Threshold file not found: {path}")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = _read_yaml(path)
    else:
        data = _read_json(path)
    if "rules" not in data or not isinstance(data["rules"], dict):
        data["rules"] = DEFAULT_THRESHOLDS["rules"]
    return data


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _is_profile_mode(mode: str) -> bool:
    return mode not in {"baseline", "unknown"}


def evaluate_thresholds(compare_report: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    rules = thresholds.get("rules", {})
    max_runner_pct = _to_float(rules.get("max_runner_duration_regression_pct"))
    min_trace_cov = _to_float(rules.get("min_trace_coverage_ratio"))
    min_gpu_ratio = _to_float(rules.get("min_gpu_util_ratio_vs_baseline"))
    allow_new = bool(rules.get("allow_new_groups", True))
    allow_missing = bool(rules.get("allow_missing_current_groups", False))
    require_values = bool(rules.get("require_metric_values", False))
    only_profile = bool(rules.get("apply_only_profile_modes", False))

    violations: list[dict[str, Any]] = []
    rows = compare_report.get("rows", [])
    if not isinstance(rows, list):
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "unknown"))
        mode = str(row.get("mode", "unknown"))
        key = str(row.get("key", "unknown"))

        if status == "new_group" and not allow_new:
            violations.append(
                {
                    "rule": "allow_new_groups",
                    "key": key,
                    "status": status,
                    "message": "new group is not allowed by threshold policy",
                }
            )
            continue

        if status == "missing_current" and not allow_missing:
            violations.append(
                {
                    "rule": "allow_missing_current_groups",
                    "key": key,
                    "status": status,
                    "message": "group exists in baseline but missing in current run",
                }
            )
            continue

        if status != "matched":
            continue
        if only_profile and not _is_profile_mode(mode):
            continue

        diff = row.get("diff", {})
        if not isinstance(diff, dict):
            diff = {}

        if max_runner_pct is not None:
            d = diff.get("avg_runner_duration_sec", {})
            pct = _to_float((d or {}).get("pct_delta"))
            if pct is None and require_values:
                violations.append(
                    {
                        "rule": "max_runner_duration_regression_pct",
                        "key": key,
                        "message": "missing pct_delta for runner duration",
                    }
                )
            elif pct is not None and pct > max_runner_pct:
                violations.append(
                    {
                        "rule": "max_runner_duration_regression_pct",
                        "key": key,
                        "value": pct,
                        "threshold": max_runner_pct,
                        "message": f"runner duration regression {pct:.4f}% > {max_runner_pct:.4f}%",
                    }
                )

        if min_trace_cov is not None:
            d = diff.get("trace_coverage_ratio", {})
            cur = _to_float((d or {}).get("current"))
            if cur is None and require_values:
                violations.append(
                    {
                        "rule": "min_trace_coverage_ratio",
                        "key": key,
                        "message": "missing current trace_coverage_ratio",
                    }
                )
            elif cur is not None and cur < min_trace_cov:
                violations.append(
                    {
                        "rule": "min_trace_coverage_ratio",
                        "key": key,
                        "value": cur,
                        "threshold": min_trace_cov,
                        "message": f"trace coverage {cur:.4f} < {min_trace_cov:.4f}",
                    }
                )

        if min_gpu_ratio is not None:
            d = diff.get("avg_gpu_util_proxy", {})
            ratio = _to_float((d or {}).get("ratio_to_baseline"))
            if ratio is None and require_values:
                violations.append(
                    {
                        "rule": "min_gpu_util_ratio_vs_baseline",
                        "key": key,
                        "message": "missing ratio_to_baseline for gpu util proxy",
                    }
                )
            elif ratio is not None and ratio < min_gpu_ratio:
                violations.append(
                    {
                        "rule": "min_gpu_util_ratio_vs_baseline",
                        "key": key,
                        "value": ratio,
                        "threshold": min_gpu_ratio,
                        "message": f"gpu util ratio {ratio:.4f} < {min_gpu_ratio:.4f}",
                    }
                )

    result = {
        "version": "threshold_check_v1",
        "created_at_epoch": time.time(),
        "pass": len(violations) == 0,
        "thresholds": thresholds,
        "summary": {
            "violations": len(violations),
            "checked_rows": len(rows),
        },
        "violations": violations,
    }
    return result

