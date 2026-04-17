from __future__ import annotations

from pathlib import Path

from .types import CaseResult


def tail_text(path: Path, max_lines: int = 60) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def summarize_tail(text: str) -> str:
    if not text.strip():
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""

    keywords = ("error", "exception", "traceback", "failed", "fatal")
    for line in reversed(lines):
        low = line.lower()
        if any(k in low for k in keywords):
            return line
    return lines[-1]


def enrich_failure_with_logs(result: CaseResult, max_lines: int = 60) -> None:
    if result.status != "failed":
        return

    # Primary log
    if result.log_path:
        primary_tail = tail_text(Path(result.log_path), max_lines=max_lines)
        if primary_tail:
            result.error_log_tail = primary_tail
            summary = summarize_tail(primary_tail)
            if summary:
                result.error_summary = summary

    # Optional side logs (mainly for PD executor)
    if result.log_path:
        logs_dir = Path(result.log_path).parent
        side_logs = [
            "prefill_server.log",
            "decode_server.log",
            "router.log",
        ]
        for name in side_logs:
            p = logs_dir / name
            t = tail_text(p, max_lines=max_lines)
            if t:
                result.extra_log_tails[name] = t
                summary = summarize_tail(t)
                if summary:
                    result.extra_log_summaries[name] = summary
