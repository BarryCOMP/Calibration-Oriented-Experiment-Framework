from __future__ import annotations

from pathlib import Path
from typing import Any


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def find_run_roots(runs_root: Path) -> list[Path]:
    runs_root = runs_root.resolve()
    if not runs_root.exists():
        return []
    out: list[Path] = []
    for d in runs_root.iterdir():
        if not d.is_dir():
            continue
        if (d / "manifests" / "run_manifest.json").exists():
            out.append(d.resolve())
    return sorted(out, key=lambda p: p.name, reverse=True)


def safe_read_json(path: Path) -> dict[str, Any]:
    import json

    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict json: {path}")
    return data


def safe_read_jsonl(path: Path) -> list[dict[str, Any]]:
    import json

    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def safe_read_csv(path: Path) -> list[dict[str, Any]]:
    import csv

    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                out.append(dict(row))
    return out

