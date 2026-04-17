from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any


def _stable_json_dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_metadata(
    run_root: Path,
    run_manifest: dict[str, Any],
    dataset_version: str,
    dataset_rows: int,
) -> dict[str, Any]:
    config_raw = run_manifest.get("config", {})
    config_digest = _sha256_text(_stable_json_dumps(config_raw))

    return {
        "schema_version": "calibration_v1",
        "dataset_version": dataset_version,
        "created_at_epoch": time.time(),
        "run_root": str(run_root.resolve()),
        "run_id": str(run_manifest.get("run_id", "unknown")),
        "config_digest_sha256": config_digest,
        "dataset_rows": int(dataset_rows),
        "total_cases": int(run_manifest.get("total_cases", 0) or 0),
        "executed_cases": int(run_manifest.get("executed_cases", 0) or 0),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "python_impl": platform.python_implementation(),
        },
    }

