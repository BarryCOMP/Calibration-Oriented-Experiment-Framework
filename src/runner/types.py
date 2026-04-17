from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    run_index: int
    params: dict[str, Any]


@dataclass(frozen=True)
class RunLayout:
    run_id: str
    run_root: Path
    logs_dir: Path
    results_dir: Path
    traces_dir: Path
    manifests_dir: Path
    cases_dir: Path


@dataclass
class CaseResult:
    case_id: str
    scenario: str
    mode: str
    status: str
    attempt: int
    command: list[str] = field(default_factory=list)
    log_path: str | None = None
    result_path: str | None = None
    trace_path: str | None = None
    started_at_epoch: float | None = None
    ended_at_epoch: float | None = None
    duration_sec: float | None = None
    notes: str | None = None
    error: str | None = None
    error_log_tail: str | None = None
    error_summary: str | None = None
    extra_log_tails: dict[str, str] = field(default_factory=dict)
    extra_log_summaries: dict[str, str] = field(default_factory=dict)
