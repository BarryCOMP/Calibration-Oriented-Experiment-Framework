from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .types import CaseResult, RunLayout


def init_manifest(config_path: str, layout: RunLayout, config_raw: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    return {
        "run_id": layout.run_id,
        "config_path": str(Path(config_path).resolve()),
        "run_root": str(layout.run_root),
        "dry_run": dry_run,
        "created_at_epoch": time.time(),
        "config": config_raw,
        "cases": [],
    }


def append_case_result(manifest: dict[str, Any], case_result: CaseResult) -> None:
    manifest["cases"].append(asdict(case_result))


def write_manifest(manifest: dict[str, Any], layout: RunLayout, filename: str = "run_manifest.json") -> Path:
    out = layout.manifests_dir / filename
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out

