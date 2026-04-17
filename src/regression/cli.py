from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .baseline_store import create_baseline, list_baselines
from .comparator import build_compare_report
from .report import render_regression_report
from .thresholds import evaluate_thresholds, load_thresholds


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict json: {path}")
    return data


def _default_threshold_path() -> Path:
    return Path("experiments/thresholds/default_thresholds.yaml").resolve()


def _resolve_thresholds(path_arg: str | None) -> tuple[dict[str, Any], str]:
    if path_arg is not None:
        p = Path(path_arg).resolve()
        return load_thresholds(p), str(p)
    default = _default_threshold_path()
    if default.exists():
        return load_thresholds(default), str(default)
    return load_thresholds(None), "builtin_default"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Regression baseline and threshold gate tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    baseline = sub.add_parser("baseline", help="Baseline management")
    bsub = baseline.add_subparsers(dest="baseline_cmd", required=True)

    b_create = bsub.add_parser("create", help="Create/overwrite a baseline snapshot")
    b_create.add_argument("--run-root", required=True)
    b_create.add_argument("--baseline-id", required=True)
    b_create.add_argument("--baselines-root", default="experiments/baselines")
    b_create.add_argument("--calibration-dir", default=None)
    b_create.add_argument("--force", action="store_true")

    b_list = bsub.add_parser("list", help="List existing baselines")
    b_list.add_argument("--baselines-root", default="experiments/baselines")

    compare = sub.add_parser("compare", help="Compare current run against a baseline")
    compare.add_argument("--run-root", required=True)
    compare.add_argument("--baseline-id", required=True)
    compare.add_argument("--baselines-root", default="experiments/baselines")
    compare.add_argument("--calibration-dir", default=None)
    compare.add_argument("--output-dir", default=None, help="Default: <run_root>/regression")
    compare.add_argument("--thresholds", default=None, help="Threshold yaml/json path")
    compare.add_argument("--fail-on-threshold", action="store_true")

    check = sub.add_parser("check", help="Threshold check from existing compare json")
    check.add_argument("--compare-json", required=True)
    check.add_argument("--thresholds", default=None, help="Threshold yaml/json path")
    check.add_argument("--output", default=None, help="Default: <compare_json_dir>/threshold_check.json")
    check.add_argument("--fail-on-threshold", action="store_true")

    return p


def _cmd_baseline_create(args: argparse.Namespace) -> int:
    summary = create_baseline(
        run_root=Path(args.run_root),
        baseline_id=str(args.baseline_id),
        baselines_root=Path(args.baselines_root),
        calibration_dir=Path(args.calibration_dir) if args.calibration_dir else None,
        force=bool(args.force),
    )
    print(f"[regression] baseline created: {summary['baseline_dir']}")
    print(f"[regression] index: {summary['index']}")
    return 0


def _cmd_baseline_list(args: argparse.Namespace) -> int:
    rows = list_baselines(Path(args.baselines_root))
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    run_root = Path(args.run_root).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else (run_root / "regression")
    output_dir.mkdir(parents=True, exist_ok=True)

    compare_report = build_compare_report(
        run_root=run_root,
        baselines_root=Path(args.baselines_root).resolve(),
        baseline_id=str(args.baseline_id),
        calibration_dir=Path(args.calibration_dir).resolve() if args.calibration_dir else None,
    )
    compare_json = output_dir / "regression_compare.json"
    _write_json(compare_json, compare_report)

    thresholds, thresholds_source = _resolve_thresholds(args.thresholds)
    threshold_check = evaluate_thresholds(compare_report, thresholds)
    threshold_check["thresholds_source"] = thresholds_source
    threshold_json = output_dir / "threshold_check.json"
    _write_json(threshold_json, threshold_check)

    report_md = output_dir / "regression_report.md"
    report_md.write_text(
        render_regression_report(compare_report, threshold_check=threshold_check),
        encoding="utf-8",
    )

    print(f"[regression] compare: {compare_json}")
    print(f"[regression] threshold: {threshold_json}")
    print(f"[regression] report: {report_md}")

    if bool(args.fail_on_threshold) and not bool(threshold_check.get("pass", False)):
        print("[regression] threshold gate failed.")
        return 2
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    compare_json = Path(args.compare_json).resolve()
    compare_report = _load_json(compare_json)

    thresholds, thresholds_source = _resolve_thresholds(args.thresholds)
    threshold_check = evaluate_thresholds(compare_report, thresholds)
    threshold_check["thresholds_source"] = thresholds_source

    output = Path(args.output).resolve() if args.output else (compare_json.parent / "threshold_check.json")
    _write_json(output, threshold_check)
    print(f"[regression] threshold: {output}")

    if bool(args.fail_on_threshold) and not bool(threshold_check.get("pass", False)):
        print("[regression] threshold gate failed.")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "baseline":
        if args.baseline_cmd == "create":
            return _cmd_baseline_create(args)
        if args.baseline_cmd == "list":
            return _cmd_baseline_list(args)
    if args.cmd == "compare":
        return _cmd_compare(args)
    if args.cmd == "check":
        return _cmd_check(args)
    raise RuntimeError(f"Unsupported command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())

