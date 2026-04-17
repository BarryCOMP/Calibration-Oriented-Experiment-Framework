from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset_builder import build_calibration_dataset
from .evaluate import evaluate_dataset_file
from .validators import validate_dataset_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Calibration pipeline: build dataset + validate + evaluate")
    p.add_argument("--run-root", required=True, help="Runner output root, e.g. experiments/runs/<run_id>")
    p.add_argument("--output", required=True, help="Output directory for calibration artifacts")
    p.add_argument(
        "--normalized-dir",
        default=None,
        help="TraceKit normalized directory. Default: <run_root>/normalized",
    )
    p.add_argument("--dataset-version", default="v1", help="Dataset version tag, e.g. v1")
    p.add_argument(
        "--auto-tracekit",
        action="store_true",
        help="Run TraceKit automatically when normalized events are missing",
    )
    p.add_argument("--nsys-bin", default="nsys", help="Path to nsys binary for TraceKit auto-run")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    run_root = Path(args.run_root).resolve()
    output_dir = Path(args.output).resolve()
    normalized_dir = Path(args.normalized_dir).resolve() if args.normalized_dir else (run_root / "normalized")
    normalized_events = normalized_dir / "normalized_events.jsonl"

    if args.auto_tracekit and not normalized_events.exists():
        from src.tracekit.cli import run_tracekit

        normalized_dir.mkdir(parents=True, exist_ok=True)
        tracekit_summary = run_tracekit(
            input_root=run_root,
            output_dir=normalized_dir,
            top_n=20,
            nsys_bin=args.nsys_bin,
            enable_nsys_rep_export=True,
        )
        print(
            "[calibration] tracekit auto-run: "
            + json.dumps(
                {
                    "num_events": tracekit_summary.get("num_events"),
                    "num_torch_files": tracekit_summary.get("num_torch_files"),
                    "num_nsys_files": tracekit_summary.get("num_nsys_files"),
                    "num_nsys_rep_files": tracekit_summary.get("num_nsys_rep_files", 0),
                },
                ensure_ascii=False,
            )
        )

    build_summary = build_calibration_dataset(
        run_root=run_root,
        output_dir=output_dir,
        normalized_dir=normalized_dir,
        dataset_version=args.dataset_version,
    )

    dataset_jsonl = Path(build_summary["dataset_jsonl"])
    validation_json = output_dir / "validation_report.json"
    evaluation_json = output_dir / "evaluation_report.json"
    evaluation_md = output_dir / "evaluation_report.md"

    validation_report = validate_dataset_file(dataset_jsonl=dataset_jsonl, output_path=validation_json)
    evaluation_report = evaluate_dataset_file(
        dataset_jsonl=dataset_jsonl,
        output_json=evaluation_json,
        output_md=evaluation_md,
    )

    final_summary = {
        "build": build_summary,
        "validation": validation_report,
        "evaluation": {
            "rows_total": evaluation_report.get("rows_total", 0),
            "groups_total": evaluation_report.get("groups_total", 0),
            "report_json": str(evaluation_json),
            "report_md": str(evaluation_md),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(final_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[calibration] dataset rows: {build_summary['dataset_rows']}")
    print(f"[calibration] dataset: {build_summary['dataset_jsonl']}")
    print(f"[calibration] validation: {validation_json}")
    print(f"[calibration] evaluation: {evaluation_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

