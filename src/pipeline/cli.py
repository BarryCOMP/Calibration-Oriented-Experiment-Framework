from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.calibration.dataset_builder import build_calibration_dataset
from src.calibration.evaluate import evaluate_dataset_file
from src.calibration.validators import validate_dataset_file
from src.regression.comparator import build_compare_report
from src.regression.report import render_regression_report
from src.regression.thresholds import evaluate_thresholds, load_thresholds
from src.runner.orchestrator import run_experiments
from src.tracekit.cli import run_tracekit


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="End-to-end pipeline: runner -> tracekit -> calibration",
    )
    p.add_argument("--config", required=True, help="Path to runner ExperimentSpec YAML.")
    p.add_argument("--output-root", default=None, help="Override runner output_root.")
    p.add_argument("--run-name", default=None, help="Override runner run_name.")
    p.add_argument("--runner-dry-run", action="store_true", help="Run runner in dry-run mode.")
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue runner cases after failures.",
    )
    p.add_argument("--trace-top-n", type=int, default=20, help="Top-N op metrics for tracekit.")
    p.add_argument("--nsys-bin", default="nsys", help="Path to nsys binary.")
    p.add_argument(
        "--disable-nsys-rep-export",
        action="store_true",
        help="Disable tracekit auto materialization for *.nsys-rep",
    )
    p.add_argument(
        "--calibration-output",
        default=None,
        help="Output directory for calibration artifacts. Default: <run_root>/calibration",
    )
    p.add_argument("--dataset-version", default="v1", help="Dataset version tag.")
    p.add_argument(
        "--regression-baseline-id",
        default=None,
        help="Optional baseline id to run regression compare/check after calibration",
    )
    p.add_argument(
        "--regression-baselines-root",
        default="experiments/baselines",
        help="Baselines root directory",
    )
    p.add_argument(
        "--regression-thresholds",
        default=None,
        help="Threshold yaml/json path. Default: experiments/thresholds/default_thresholds.yaml if exists.",
    )
    p.add_argument(
        "--fail-on-regression-threshold",
        action="store_true",
        help="Return non-zero when regression threshold check fails.",
    )
    return p


def run_full_pipeline(
    config: str | Path,
    output_root: str | None = None,
    run_name: str | None = None,
    runner_dry_run: bool = False,
    continue_on_error: bool = False,
    trace_top_n: int = 20,
    nsys_bin: str = "nsys",
    enable_nsys_rep_export: bool = True,
    calibration_output: str | Path | None = None,
    dataset_version: str = "v1",
    regression_baseline_id: str | None = None,
    regression_baselines_root: str | Path = "experiments/baselines",
    regression_thresholds: str | Path | None = None,
) -> dict[str, Any]:
    manifest_path = run_experiments(
        config_path=Path(config),
        dry_run=runner_dry_run,
        continue_on_error=continue_on_error,
        output_root_override=output_root,
        run_name_override=run_name,
    ).resolve()
    run_root = manifest_path.parent.parent

    normalized_dir = run_root / "normalized"
    trace_summary = run_tracekit(
        input_root=run_root,
        output_dir=normalized_dir,
        top_n=trace_top_n,
        nsys_bin=nsys_bin,
        enable_nsys_rep_export=enable_nsys_rep_export,
    )

    calibration_dir = Path(calibration_output).resolve() if calibration_output else (run_root / "calibration")
    calibration_build = build_calibration_dataset(
        run_root=run_root,
        output_dir=calibration_dir,
        normalized_dir=normalized_dir,
        dataset_version=dataset_version,
    )
    dataset_jsonl = Path(calibration_build["dataset_jsonl"])
    validation_json = calibration_dir / "validation_report.json"
    evaluation_json = calibration_dir / "evaluation_report.json"
    evaluation_md = calibration_dir / "evaluation_report.md"
    validation_report = validate_dataset_file(dataset_jsonl=dataset_jsonl, output_path=validation_json)
    evaluation_report = evaluate_dataset_file(
        dataset_jsonl=dataset_jsonl,
        output_json=evaluation_json,
        output_md=evaluation_md,
    )

    summary = {
        "manifest_path": str(manifest_path),
        "run_root": str(run_root),
        "normalized_dir": str(normalized_dir),
        "calibration_dir": str(calibration_dir),
        "runner_dry_run": runner_dry_run,
        "runner": {
            "run_id": calibration_build.get("run_id", "unknown"),
        },
        "tracekit": trace_summary,
        "calibration": {
            "build": calibration_build,
            "validation": validation_report,
            "evaluation": {
                "rows_total": evaluation_report.get("rows_total", 0),
                "groups_total": evaluation_report.get("groups_total", 0),
                "report_json": str(evaluation_json),
                "report_md": str(evaluation_md),
            },
        },
    }

    if regression_baseline_id:
        regression_dir = run_root / "regression"
        regression_dir.mkdir(parents=True, exist_ok=True)
        compare_report = build_compare_report(
            run_root=run_root,
            baselines_root=Path(regression_baselines_root).resolve(),
            baseline_id=str(regression_baseline_id),
            calibration_dir=calibration_dir,
        )
        compare_json = regression_dir / "regression_compare.json"
        compare_json.write_text(json.dumps(compare_report, indent=2, ensure_ascii=False), encoding="utf-8")

        thresholds_path = None
        if regression_thresholds is not None:
            thresholds_path = Path(regression_thresholds).resolve()
        else:
            default_th = Path("experiments/thresholds/default_thresholds.yaml").resolve()
            if default_th.exists():
                thresholds_path = default_th
        thresholds = load_thresholds(thresholds_path)
        threshold_check = evaluate_thresholds(compare_report, thresholds)
        threshold_check["thresholds_source"] = str(thresholds_path) if thresholds_path else "builtin_default"
        threshold_json = regression_dir / "threshold_check.json"
        threshold_json.write_text(json.dumps(threshold_check, indent=2, ensure_ascii=False), encoding="utf-8")

        report_md = regression_dir / "regression_report.md"
        report_md.write_text(render_regression_report(compare_report, threshold_check), encoding="utf-8")
        summary["regression"] = {
            "baseline_id": regression_baseline_id,
            "baselines_root": str(Path(regression_baselines_root).resolve()),
            "compare_json": str(compare_json),
            "threshold_json": str(threshold_json),
            "report_md": str(report_md),
            "pass": bool(threshold_check.get("pass", False)),
            "violations": int(threshold_check.get("summary", {}).get("violations", 0)),
        }

    summary_path = calibration_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run_full_pipeline(
        config=args.config,
        output_root=args.output_root,
        run_name=args.run_name,
        runner_dry_run=args.runner_dry_run,
        continue_on_error=args.continue_on_error,
        trace_top_n=args.trace_top_n,
        nsys_bin=args.nsys_bin,
        enable_nsys_rep_export=not args.disable_nsys_rep_export,
        calibration_output=args.calibration_output,
        dataset_version=args.dataset_version,
        regression_baseline_id=args.regression_baseline_id,
        regression_baselines_root=args.regression_baselines_root,
        regression_thresholds=args.regression_thresholds,
    )
    print(f"[pipeline] run_root: {summary['run_root']}")
    print(f"[pipeline] trace events: {summary['tracekit'].get('num_events', 0)}")
    print(f"[pipeline] calibration rows: {summary['calibration']['build'].get('dataset_rows', 0)}")
    if "regression" in summary:
        print(f"[pipeline] regression pass: {summary['regression'].get('pass')}")
        print(f"[pipeline] regression violations: {summary['regression'].get('violations')}")
    print(f"[pipeline] summary: {summary['summary_path']}")
    if args.fail_on_regression_threshold and "regression" in summary and not summary["regression"].get("pass", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
