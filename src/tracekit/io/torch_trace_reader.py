from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TorchTrace:
    path: Path
    events: list[dict[str, Any]]
    metadata: dict[str, Any]


def discover_torch_trace_files(input_root: Path) -> list[Path]:
    out: list[Path] = []
    patterns = ["*.trace.json", "*.trace.json.gz"]
    for pat in patterns:
        out.extend(input_root.rglob(pat))
    return sorted({p.resolve() for p in out})


def _load_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    else:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected torch trace format (expect dict): {path}")
    return data


def read_torch_trace(path: Path) -> TorchTrace:
    data = _load_json(path)
    events = data.get("traceEvents", [])
    if not isinstance(events, list):
        raise ValueError(f"Unexpected torch traceEvents type in {path}")
    metadata = {
        "schemaVersion": data.get("schemaVersion"),
        "trace_id": data.get("trace_id"),
        "baseTimeNanoseconds": data.get("baseTimeNanoseconds"),
        "deviceProperties": data.get("deviceProperties", []),
        "distributedInfo": data.get("distributedInfo", {}),
    }
    return TorchTrace(path=path, events=events, metadata=metadata)

