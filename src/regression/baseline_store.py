from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .schema import GroupKey


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict json: {path}")
    return data


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_calibration_dir(run_root: Path, calibration_dir: Path | None = None) -> Path:
    if calibration_dir is not None:
        p = calibration_dir.resolve()
        if not p.exists():
            raise FileNotFoundError(f"Calibration dir not found: {p}")
        return p
    default_dir = run_root.resolve() / "calibration"
    if default_dir.exists():
        return default_dir
    raise FileNotFoundError(
        f"Calibration dir not found under run root: {run_root}. "
        "Expected <run_root>/calibration"
    )


def _index_path(baselines_root: Path) -> Path:
    return baselines_root / "baseline_index.json"


def load_baseline_index(baselines_root: Path) -> dict[str, Any]:
    p = _index_path(baselines_root)
    if not p.exists():
        return {"version": "v1", "baselines": []}
    data = _read_json(p)
    if "baselines" not in data or not isinstance(data["baselines"], list):
        data["baselines"] = []
    if "version" not in data:
        data["version"] = "v1"
    return data


def save_baseline_index(baselines_root: Path, index: dict[str, Any]) -> Path:
    p = _index_path(baselines_root)
    _write_json(p, index)
    return p


def list_baselines(baselines_root: Path) -> list[dict[str, Any]]:
    index = load_baseline_index(baselines_root)
    baselines = [b for b in index.get("baselines", []) if isinstance(b, dict)]
    return sorted(baselines, key=lambda x: float(x.get("created_at_epoch", 0.0)), reverse=True)


def get_baseline_entry(baselines_root: Path, baseline_id: str) -> dict[str, Any]:
    for b in list_baselines(baselines_root):
        if str(b.get("baseline_id", "")) == baseline_id:
            return b
    raise KeyError(f"Baseline not found: {baseline_id}")


def _groups_to_map(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for g in groups:
        if not isinstance(g, dict):
            continue
        k = GroupKey.from_row(g).to_string()
        out[k] = g
    return out


def create_baseline(
    run_root: Path,
    baseline_id: str,
    baselines_root: Path,
    calibration_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    baselines_root = baselines_root.resolve()
    cal_dir = resolve_calibration_dir(run_root, calibration_dir)

    eval_path = cal_dir / "evaluation_report.json"
    if not eval_path.exists():
        raise FileNotFoundError(
            f"Missing evaluation report: {eval_path}. "
            "Please run calibration pipeline first."
        )
    evaluation = _read_json(eval_path)
    groups = evaluation.get("groups", [])
    if not isinstance(groups, list):
        groups = []

    metadata_path = cal_dir / "metadata.json"
    metadata = _read_json(metadata_path) if metadata_path.exists() else {}

    validation_path = cal_dir / "validation_report.json"
    validation = _read_json(validation_path) if validation_path.exists() else {}

    summary_path = cal_dir / "summary.json"
    summary = _read_json(summary_path) if summary_path.exists() else {}

    run_id = str(metadata.get("run_id", run_root.name))
    target_dir = baselines_root / baseline_id
    if target_dir.exists() and not force:
        raise FileExistsError(
            f"Baseline already exists: {target_dir}. "
            "Use force=True to overwrite."
        )
    target_dir.mkdir(parents=True, exist_ok=True)

    metrics_summary = {
        "groups": groups,
        "groups_map": _groups_to_map(groups),
        "rows_total": int(evaluation.get("rows_total", 0) or 0),
        "groups_total": int(evaluation.get("groups_total", 0) or 0),
    }
    baseline_metadata = {
        "baseline_id": baseline_id,
        "created_at_epoch": time.time(),
        "source_run_root": str(run_root),
        "source_calibration_dir": str(cal_dir),
        "run_id": run_id,
        "config_digest_sha256": metadata.get("config_digest_sha256"),
        "schema_version": "regression_baseline_v1",
        "validation": validation,
    }
    snapshot = {
        "metadata": baseline_metadata,
        "evaluation": evaluation,
        "calibration_summary": summary,
        "calibration_metadata": metadata,
    }

    _write_json(target_dir / "metrics_summary.json", metrics_summary)
    _write_json(target_dir / "metadata.json", baseline_metadata)
    _write_json(target_dir / "baseline_snapshot.json", snapshot)

    index = load_baseline_index(baselines_root)
    baselines = [b for b in index.get("baselines", []) if isinstance(b, dict)]
    baselines = [b for b in baselines if str(b.get("baseline_id", "")) != baseline_id]
    baselines.append(
        {
            "baseline_id": baseline_id,
            "run_id": run_id,
            "path": str(target_dir),
            "created_at_epoch": baseline_metadata["created_at_epoch"],
            "config_digest_sha256": baseline_metadata.get("config_digest_sha256"),
        }
    )
    index["baselines"] = sorted(
        baselines,
        key=lambda x: float(x.get("created_at_epoch", 0.0)),
        reverse=True,
    )
    save_baseline_index(baselines_root, index)

    return {
        "baseline_id": baseline_id,
        "run_id": run_id,
        "baseline_dir": str(target_dir),
        "metrics_summary": str(target_dir / "metrics_summary.json"),
        "metadata": str(target_dir / "metadata.json"),
        "snapshot": str(target_dir / "baseline_snapshot.json"),
        "index": str(_index_path(baselines_root)),
    }

