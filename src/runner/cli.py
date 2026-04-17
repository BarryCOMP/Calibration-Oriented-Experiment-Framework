from __future__ import annotations

import argparse
from pathlib import Path

from .orchestrator import run_experiments


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase A experiment runner (MVP skeleton).")
    p.add_argument("--config", required=True, help="Path to ExperimentSpec YAML.")
    p.add_argument("--dry-run", action="store_true", help="Prepare commands only.")
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue remaining cases after a failure.",
    )
    p.add_argument(
        "--output-root",
        default=None,
        help="Override output_root from config.",
    )
    p.add_argument(
        "--run-name",
        default=None,
        help="Override run_name from config.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = run_experiments(
        config_path=Path(args.config),
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        output_root_override=args.output_root,
        run_name_override=args.run_name,
    )
    print(f"[runner] done: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

