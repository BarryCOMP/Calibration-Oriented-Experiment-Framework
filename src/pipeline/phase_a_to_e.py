from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from src.dashboard.charts import build_overhead_rows, build_pareto_rows, build_stage_stacked_rows
from src.dashboard.data_loader import discover_runs, load_run_bundle
from src.pipeline.cli import run_full_pipeline
from src.regression.baseline_store import create_baseline


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_phase_a_to_e_round(
    config: str | Path,
    work_root: str | Path = "step_reports/phase_a_to_e_rounds",
    runner_dry_run: bool = True,
    nsys_bin: str = "nsys",
    trace_top_n: int = 20,
    fail_on_regression_threshold: bool = False,
) -> dict[str, Any]:
    config_path = Path(config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    work_root = Path(work_root).resolve()
    round_id = time.strftime("round_%Y%m%dT%H%M%S")
    round_root = work_root / round_id
    runs_root = round_root / "runs"
    baselines_root = round_root / "baselines"
    thresholds_path = Path("experiments/thresholds/default_thresholds.yaml").resolve()

    # Phase A/B/C: baseline run
    baseline_summary = run_full_pipeline(
        config=config_path,
        output_root=str(runs_root),
        run_name=f"{round_id}_baseline",
        runner_dry_run=runner_dry_run,
        continue_on_error=False,
        trace_top_n=trace_top_n,
        nsys_bin=nsys_bin,
        enable_nsys_rep_export=False,
        dataset_version="v1",
    )
    baseline_run_root = Path(baseline_summary["run_root"]).resolve()

    # Phase D: create baseline snapshot from this round
    baseline_id = f"{round_id}_ref"
    baseline_create = create_baseline(
        run_root=baseline_run_root,
        baseline_id=baseline_id,
        baselines_root=baselines_root,
        force=True,
    )

    # Phase A/B/C/D: current run + regression compare/check against baseline from this round
    current_summary = run_full_pipeline(
        config=config_path,
        output_root=str(runs_root),
        run_name=f"{round_id}_current",
        runner_dry_run=runner_dry_run,
        continue_on_error=False,
        trace_top_n=trace_top_n,
        nsys_bin=nsys_bin,
        enable_nsys_rep_export=False,
        dataset_version="v1",
        regression_baseline_id=baseline_id,
        regression_baselines_root=baselines_root,
        regression_thresholds=thresholds_path,
    )
    current_run_root = Path(current_summary["run_root"]).resolve()
    regression = current_summary.get("regression", {})
    regression_pass = bool(regression.get("pass", False))

    # Phase E: dashboard data chain check using runs generated in this round
    runs = discover_runs(runs_root)
    bundle = load_run_bundle(current_run_root)
    calibration_rows = bundle.get("calibration_rows", [])
    if not isinstance(calibration_rows, list):
        calibration_rows = []
    overhead_rows = build_overhead_rows(bundle)
    stacked_rows = build_stage_stacked_rows(calibration_rows)
    pareto_rows = build_pareto_rows(calibration_rows)

    dashboard_summary = {
        "runs_discovered": len(runs),
        "current_run_id": bundle.get("manifest", {}).get("run_id"),
        "calibration_rows": len(calibration_rows),
        "overhead_rows": len(overhead_rows),
        "stacked_rows": len(stacked_rows),
        "pareto_rows": len(pareto_rows),
    }
    _write_json(round_root / "dashboard_data_summary.json", dashboard_summary)

    summary = {
        "round_id": round_id,
        "round_root": str(round_root),
        "config": str(config_path),
        "runner_dry_run": runner_dry_run,
        "phase_a_b_c_baseline": {
            "run_root": str(baseline_run_root),
            "pipeline_summary": baseline_summary.get("summary_path"),
        },
        "phase_d_baseline_create": baseline_create,
        "phase_a_b_c_d_current": {
            "run_root": str(current_run_root),
            "pipeline_summary": current_summary.get("summary_path"),
            "regression": regression,
        },
        "phase_e_dashboard": dashboard_summary,
        "artifacts": {
            "round_summary": str(round_root / "round_summary.json"),
            "dashboard_data_summary": str(round_root / "dashboard_data_summary.json"),
            "baseline_index": str(baselines_root / "baseline_index.json"),
        },
    }
    _write_json(round_root / "round_summary.json", summary)

    if fail_on_regression_threshold and not regression_pass:
        summary["exit_code"] = 2
    else:
        summary["exit_code"] = 0
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run one full round from Phase A to E with generated artifacts chained across phases."
    )
    p.add_argument("--config", required=True, help="ExperimentSpec yaml for runner.")
    p.add_argument("--work-root", default="step_reports/phase_a_to_e_rounds", help="Root dir for this test round.")
    p.add_argument(
        "--runner-dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use runner dry-run (default true).",
    )
    p.add_argument("--nsys-bin", default="nsys", help="Path to nsys binary.")
    p.add_argument("--trace-top-n", type=int, default=20)
    p.add_argument("--fail-on-regression-threshold", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run_phase_a_to_e_round(
        config=args.config,
        work_root=args.work_root,
        runner_dry_run=bool(args.runner_dry_run),
        nsys_bin=args.nsys_bin,
        trace_top_n=int(args.trace_top_n),
        fail_on_regression_threshold=bool(args.fail_on_regression_threshold),
    )
    print(f"[a2e] round_root: {summary['round_root']}")
    print(f"[a2e] baseline_run: {summary['phase_a_b_c_baseline']['run_root']}")
    print(f"[a2e] current_run: {summary['phase_a_b_c_d_current']['run_root']}")
    print(f"[a2e] regression_pass: {summary['phase_a_b_c_d_current']['regression'].get('pass')}")
    print(f"[a2e] dashboard_rows: {summary['phase_e_dashboard']['calibration_rows']}")
    print(f"[a2e] summary: {summary['artifacts']['round_summary']}")
    return int(summary.get("exit_code", 0) or 0)


if __name__ == "__main__":
    raise SystemExit(main())

