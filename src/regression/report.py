from __future__ import annotations

from typing import Any


def _fnum(v: Any, nd: int = 4) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{nd}f}"
    except Exception:
        return "n/a"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render_regression_report(compare_report: dict[str, Any], threshold_check: dict[str, Any] | None = None) -> str:
    lines: list[str] = []
    lines.append("# Regression Report")
    lines.append("")

    baseline = compare_report.get("baseline", {})
    summary = compare_report.get("summary", {})
    lines.append(f"- baseline_id: {baseline.get('baseline_id', 'unknown')}")
    lines.append(f"- current_run_root: {compare_report.get('current', {}).get('run_root', 'unknown')}")
    lines.append(f"- matched_groups: {summary.get('matched_groups', 0)}")
    lines.append(f"- new_groups: {summary.get('new_groups', 0)}")
    lines.append(f"- missing_current_groups: {summary.get('missing_current_groups', 0)}")
    lines.append("")

    rows = compare_report.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    matched = [r for r in rows if isinstance(r, dict) and str(r.get("status", "")) == "matched"]

    lines.append("## Group Diffs")
    md_rows: list[list[str]] = []
    for r in matched:
        d = r.get("diff", {})
        runner = (d or {}).get("avg_runner_duration_sec", {})
        cov = (d or {}).get("trace_coverage_ratio", {})
        gpu = (d or {}).get("avg_gpu_util_proxy", {})
        md_rows.append(
            [
                str(r.get("scenario", "unknown")),
                str(r.get("mode", "unknown")),
                str(r.get("phase", "unknown")),
                _fnum((runner or {}).get("baseline"), 6),
                _fnum((runner or {}).get("current"), 6),
                _fnum((runner or {}).get("pct_delta"), 2),
                _fnum((cov or {}).get("baseline"), 4),
                _fnum((cov or {}).get("current"), 4),
                _fnum((gpu or {}).get("ratio_to_baseline"), 4),
            ]
        )
    if md_rows:
        lines.append(
            _md_table(
                [
                    "scenario",
                    "mode",
                    "phase",
                    "runner_baseline_sec",
                    "runner_current_sec",
                    "runner_pct_delta",
                    "coverage_baseline",
                    "coverage_current",
                    "gpu_ratio_to_baseline",
                ],
                md_rows,
            )
        )
    else:
        lines.append("No matched groups to compare.")
    lines.append("")

    lines.append("## Threshold Check")
    if threshold_check is None:
        lines.append("No threshold check provided.")
    else:
        ok = bool(threshold_check.get("pass", False))
        lines.append(f"- pass: {ok}")
        lines.append(f"- violations: {threshold_check.get('summary', {}).get('violations', 0)}")
        vrows = threshold_check.get("violations", [])
        if isinstance(vrows, list) and vrows:
            vtable: list[list[str]] = []
            for v in vrows:
                if not isinstance(v, dict):
                    continue
                vtable.append(
                    [
                        str(v.get("rule", "unknown")),
                        str(v.get("key", "unknown")),
                        str(v.get("message", "")),
                    ]
                )
            if vtable:
                lines.append("")
                lines.append(_md_table(["rule", "key", "message"], vtable))
    lines.append("")

    return "\n".join(lines)

