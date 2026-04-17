from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("scenario", "unknown")),
        str(row.get("mode", "unknown")),
        str(row.get("phase", "unknown")),
    )


def build_evaluation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        k = _group_key(r)
        g = grouped.get(k)
        if g is None:
            g = {
                "scenario": k[0],
                "mode": k[1],
                "phase": k[2],
                "samples": 0,
                "avg_runner_duration_sec": 0.0,
                "avg_trace_time_us": 0.0,
                "avg_gpu_util_proxy": 0.0,
                "trace_coverage_ratio": 0.0,
            }
            grouped[k] = g
        g["samples"] += 1
        g["avg_runner_duration_sec"] += _as_float(r.get("runner_duration_sec", 0.0))
        g["avg_trace_time_us"] += _as_float(r.get("total_trace_time_us", 0.0))
        g["avg_gpu_util_proxy"] += _as_float(r.get("gpu_util_proxy", 0.0))
        g["trace_coverage_ratio"] += _as_float(r.get("trace_coverage", 0.0))

    groups = list(grouped.values())
    for g in groups:
        n = max(1, int(g["samples"]))
        g["avg_runner_duration_sec"] /= n
        g["avg_trace_time_us"] /= n
        g["avg_gpu_util_proxy"] /= n
        g["trace_coverage_ratio"] /= n

    # Simple overhead view: compare against baseline in same scenario+phase.
    baseline_index: dict[tuple[str, str], dict[str, Any]] = {}
    for g in groups:
        if g["mode"] == "baseline":
            baseline_index[(g["scenario"], g["phase"])] = g

    overhead_rows: list[dict[str, Any]] = []
    for g in groups:
        base = baseline_index.get((g["scenario"], g["phase"]))
        if base is None or g["mode"] == "baseline":
            continue
        base_t = _as_float(base.get("avg_runner_duration_sec", 0.0))
        cur_t = _as_float(g.get("avg_runner_duration_sec", 0.0))
        overhead_rows.append(
            {
                "scenario": g["scenario"],
                "phase": g["phase"],
                "mode": g["mode"],
                "baseline_mode": "baseline",
                "runner_time_overhead_ratio": (cur_t / base_t) if base_t > 0 else None,
                "runner_time_overhead_pct": ((cur_t - base_t) / base_t * 100.0) if base_t > 0 else None,
            }
        )

    summary = {
        "rows_total": len(rows),
        "groups_total": len(groups),
        "groups": sorted(groups, key=lambda x: (x["scenario"], x["mode"], x["phase"])),
        "overhead_vs_baseline": sorted(overhead_rows, key=lambda x: (x["scenario"], x["mode"], x["phase"])),
    }
    return summary


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render_markdown_report(report: dict[str, Any]) -> str:
    groups = report.get("groups", [])
    overhead = report.get("overhead_vs_baseline", [])

    lines = ["# Calibration Evaluation Report", ""]
    lines.append(f"- rows_total: {report.get('rows_total', 0)}")
    lines.append(f"- groups_total: {report.get('groups_total', 0)}")
    lines.append("")

    lines.append("## Group Summary")
    g_rows: list[list[str]] = []
    for g in groups:
        g_rows.append(
            [
                str(g["scenario"]),
                str(g["mode"]),
                str(g["phase"]),
                str(g["samples"]),
                f"{_as_float(g['avg_runner_duration_sec']):.6f}",
                f"{_as_float(g['avg_trace_time_us']):.2f}",
                f"{_as_float(g['avg_gpu_util_proxy']):.4f}",
                f"{_as_float(g['trace_coverage_ratio']):.4f}",
            ]
        )
    lines.append(
        _md_table(
            [
                "scenario",
                "mode",
                "phase",
                "samples",
                "avg_runner_duration_sec",
                "avg_trace_time_us",
                "avg_gpu_util_proxy",
                "trace_coverage_ratio",
            ],
            g_rows,
        )
    )
    lines.append("")

    lines.append("## Overhead Vs Baseline")
    if overhead:
        o_rows: list[list[str]] = []
        for o in overhead:
            ratio = o["runner_time_overhead_ratio"]
            pct = o["runner_time_overhead_pct"]
            o_rows.append(
                [
                    str(o["scenario"]),
                    str(o["phase"]),
                    str(o["mode"]),
                    "baseline",
                    "n/a" if ratio is None else f"{_as_float(ratio):.4f}",
                    "n/a" if pct is None else f"{_as_float(pct):.2f}",
                ]
            )
        lines.append(
            _md_table(
                ["scenario", "phase", "mode", "baseline_mode", "overhead_ratio", "overhead_pct"],
                o_rows,
            )
        )
    else:
        lines.append("No baseline-comparable groups found.")
    lines.append("")
    return "\n".join(lines)


def evaluate_dataset_file(
    dataset_jsonl: Path,
    output_json: Path | None = None,
    output_md: Path | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with dataset_jsonl.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                r = json.loads(text)
            except Exception:
                continue
            if isinstance(r, dict):
                rows.append(r)

    report = build_evaluation(rows)
    if output_json is not None:
        output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_md is not None:
        output_md.write_text(render_markdown_report(report), encoding="utf-8")
    return report

