from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .types import RunLayout


def _utc_stamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def create_run_layout(output_root: str | Path, run_name: str) -> RunLayout:
    root = Path(output_root).resolve()
    run_id = f"{run_name}_{_utc_stamp()}"
    run_root = root / run_id

    logs_dir = run_root / "logs"
    results_dir = run_root / "results"
    traces_dir = run_root / "traces"
    manifests_dir = run_root / "manifests"
    cases_dir = run_root / "cases"

    for p in (logs_dir, results_dir, traces_dir, manifests_dir, cases_dir):
        p.mkdir(parents=True, exist_ok=True)

    return RunLayout(
        run_id=run_id,
        run_root=run_root,
        logs_dir=logs_dir,
        results_dir=results_dir,
        traces_dir=traces_dir,
        manifests_dir=manifests_dir,
        cases_dir=cases_dir,
    )


@dataclass(frozen=True)
class CasePaths:
    case_root: Path
    logs_dir: Path
    results_dir: Path
    traces_dir: Path
    log_file: Path
    result_file: Path


def prepare_case_paths(layout: RunLayout, case_id: str) -> CasePaths:
    case_root = layout.cases_dir / case_id
    logs_dir = case_root / "logs"
    results_dir = case_root / "results"
    traces_dir = case_root / "traces"
    for p in (logs_dir, results_dir, traces_dir):
        p.mkdir(parents=True, exist_ok=True)
    return CasePaths(
        case_root=case_root,
        logs_dir=logs_dir,
        results_dir=results_dir,
        traces_dir=traces_dir,
        log_file=logs_dir / "run.log",
        result_file=results_dir / "result.jsonl",
    )

