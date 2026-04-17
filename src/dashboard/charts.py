from __future__ import annotations

from collections import defaultdict
from typing import Any

from .utils import to_float


def _matches(value: str, allowed: set[str] | None) -> bool:
    if allowed is None or len(allowed) == 0:
        return True
    return value in allowed


def filter_rows(
    rows: list[dict[str, Any]],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sc = str(r.get("scenario", "unknown"))
        md = str(r.get("mode", "unknown"))
        ph = str(r.get("phase", "unknown"))
        if not _matches(sc, scenarios):
            continue
        if not _matches(md, modes):
            continue
        if not _matches(ph, phases):
            continue
        out.append(r)
    return out


def build_overhead_rows(
    bundle: dict[str, Any],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    reg = bundle.get("regression_compare")
    if isinstance(reg, dict):
        rows = reg.get("rows", [])
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                if str(r.get("status", "")) != "matched":
                    continue
                sc = str(r.get("scenario", "unknown"))
                md = str(r.get("mode", "unknown"))
                ph = str(r.get("phase", "unknown"))
                if md == "baseline":
                    continue
                if not _matches(sc, scenarios) or not _matches(md, modes) or not _matches(ph, phases):
                    continue
                d = ((r.get("diff") or {}).get("avg_runner_duration_sec") or {})
                out.append(
                    {
                        "scenario": sc,
                        "mode": md,
                        "phase": ph,
                        "overhead_pct": to_float(d.get("pct_delta")),
                        "overhead_ratio": to_float(d.get("ratio_to_baseline")),
                    }
                )
        if out:
            return out

    # fallback to calibration overhead view
    eval_report = bundle.get("calibration_eval")
    if isinstance(eval_report, dict):
        rows = eval_report.get("overhead_vs_baseline", [])
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                sc = str(r.get("scenario", "unknown"))
                md = str(r.get("mode", "unknown"))
                ph = str(r.get("phase", "unknown"))
                if not _matches(sc, scenarios) or not _matches(md, modes) or not _matches(ph, phases):
                    continue
                out.append(
                    {
                        "scenario": sc,
                        "mode": md,
                        "phase": ph,
                        "overhead_pct": to_float(r.get("runner_time_overhead_pct")),
                        "overhead_ratio": to_float(r.get("runner_time_overhead_ratio")),
                    }
                )
    return out


def build_stage_stacked_rows(
    calibration_rows: list[dict[str, Any]],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = filter_rows(calibration_rows, scenarios=scenarios, modes=modes, phases=phases)
    agg: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))

    fields = [
        "compute_time_us",
        "comm_time_us",
        "memory_time_us",
        "scheduler_time_us",
        "idle_time_us",
        "other_time_us",
    ]

    for r in rows:
        k = (str(r.get("scenario", "unknown")), str(r.get("mode", "unknown")), str(r.get("phase", "unknown")))
        for f in fields:
            agg[k][f] += to_float(r.get(f)) or 0.0

    out: list[dict[str, Any]] = []
    for (sc, md, ph), vals in agg.items():
        for f in fields:
            out.append(
                {
                    "scenario": sc,
                    "mode": md,
                    "phase": ph,
                    "component": f.replace("_time_us", ""),
                    "value_us": float(vals.get(f, 0.0)),
                }
            )
    out.sort(key=lambda x: (x["scenario"], x["mode"], x["phase"], x["component"]))
    return out


def build_stage_stacked_rows_relative(
    calibration_rows: list[dict[str, Any]],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    abs_rows = build_stage_stacked_rows(
        calibration_rows,
        scenarios=scenarios,
        modes=modes,
        phases=phases,
    )
    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    for r in abs_rows:
        key = (str(r["scenario"]), str(r["mode"]), str(r["phase"]))
        totals[key] += float(r.get("value_us", 0.0) or 0.0)

    out: list[dict[str, Any]] = []
    for r in abs_rows:
        key = (str(r["scenario"]), str(r["mode"]), str(r["phase"]))
        total = totals.get(key, 0.0)
        pct = (float(r.get("value_us", 0.0) or 0.0) / total * 100.0) if total > 0 else 0.0
        out.append(
            {
                "scenario": r["scenario"],
                "mode": r["mode"],
                "phase": r["phase"],
                "component": r["component"],
                "value_us": float(r.get("value_us", 0.0) or 0.0),
                "value_pct": pct,
            }
        )
    return out


def build_pareto_rows(
    calibration_rows: list[dict[str, Any]],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = filter_rows(calibration_rows, scenarios=scenarios, modes=modes, phases=phases)
    agg: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cnt: dict[tuple[str, str, str], int] = defaultdict(int)

    for r in rows:
        k = (str(r.get("scenario", "unknown")), str(r.get("mode", "unknown")), str(r.get("phase", "unknown")))
        thr = to_float(r.get("throughput_metric"))
        lat = to_float(r.get("latency_metric_ms"))
        if thr is None or lat is None:
            continue
        agg[k]["throughput"] += thr
        agg[k]["latency_ms"] += lat
        cnt[k] += 1

    out: list[dict[str, Any]] = []
    for k, n in cnt.items():
        if n <= 0:
            continue
        sc, md, ph = k
        out.append(
            {
                "scenario": sc,
                "mode": md,
                "phase": ph,
                "throughput": agg[k]["throughput"] / n,
                "latency_ms": agg[k]["latency_ms"] / n,
                "samples": n,
            }
        )
    out.sort(key=lambda x: (x["scenario"], x["mode"], x["phase"]))
    return out


def build_component_share_rows(
    calibration_rows: list[dict[str, Any]],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = filter_rows(calibration_rows, scenarios=scenarios, modes=modes, phases=phases)
    fields = [
        "compute_time_us",
        "comm_time_us",
        "memory_time_us",
        "scheduler_time_us",
        "idle_time_us",
        "other_time_us",
    ]
    totals: dict[str, float] = defaultdict(float)
    grand_total = 0.0
    for r in rows:
        for f in fields:
            v = to_float(r.get(f)) or 0.0
            name = f.replace("_time_us", "")
            totals[name] += v
            grand_total += v

    out: list[dict[str, Any]] = []
    for name in sorted(totals.keys()):
        us = float(totals[name])
        pct = us / grand_total * 100.0 if grand_total > 0 else 0.0
        out.append({"component": name, "value_us": us, "value_pct": pct})
    return out


def build_mode_summary_rows(
    calibration_rows: list[dict[str, Any]],
    scenarios: set[str] | None = None,
    modes: set[str] | None = None,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = filter_rows(calibration_rows, scenarios=scenarios, modes=modes, phases=phases)
    agg: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cnt: dict[tuple[str, str], int] = defaultdict(int)
    cnt_thr: dict[tuple[str, str], int] = defaultdict(int)
    cnt_lat: dict[tuple[str, str], int] = defaultdict(int)
    cnt_gpu: dict[tuple[str, str], int] = defaultdict(int)

    for r in rows:
        key = (str(r.get("scenario", "unknown")), str(r.get("mode", "unknown")))
        cnt[key] += 1
        dur = to_float(r.get("runner_duration_sec"))
        if dur is not None:
            agg[key]["runner_duration_sec"] += dur

        thr = to_float(r.get("throughput_metric"))
        if thr is not None:
            agg[key]["throughput"] += thr
            cnt_thr[key] += 1

        lat = to_float(r.get("latency_metric_ms"))
        if lat is not None:
            agg[key]["latency_ms"] += lat
            cnt_lat[key] += 1

        gpu = to_float(r.get("gpu_util_proxy"))
        if gpu is not None:
            agg[key]["gpu_util_proxy"] += gpu
            cnt_gpu[key] += 1

    out: list[dict[str, Any]] = []
    for key in sorted(cnt.keys()):
        sc, md = key
        n = cnt[key]
        out.append(
            {
                "scenario": sc,
                "mode": md,
                "samples": n,
                "avg_runner_duration_sec": agg[key]["runner_duration_sec"] / n if n > 0 else None,
                "avg_throughput": agg[key]["throughput"] / cnt_thr[key] if cnt_thr[key] > 0 else None,
                "avg_latency_ms": agg[key]["latency_ms"] / cnt_lat[key] if cnt_lat[key] > 0 else None,
                "avg_gpu_util_proxy": agg[key]["gpu_util_proxy"] / cnt_gpu[key] if cnt_gpu[key] > 0 else None,
            }
        )
    return out


def make_overhead_figure(rows: list[dict[str, Any]]):
    import plotly.express as px  # type: ignore

    if not rows:
        return None
    prepared = []
    for r in rows:
        row = dict(r)
        row["label"] = f"{row['scenario']}/{row['phase']}"
        prepared.append(row)
    x_points = len({str(r["label"]) for r in prepared})
    use_bar = len(prepared) <= 4 or x_points <= 2
    if use_bar:
        fig = px.bar(
            prepared,
            x="label",
            y="overhead_pct",
            color="mode",
            barmode="group",
            title="Overhead Comparison (Sparse Cases)",
            text="overhead_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    else:
        fig = px.line(
            prepared,
            x="label",
            y="overhead_pct",
            color="mode",
            markers=True,
            title="Overhead Curve (Runner Duration % vs Baseline)",
        )
    fig.add_hline(y=0.0, line_dash="dot")
    fig.update_layout(template="plotly_white", xaxis_title="scenario/phase", yaxis_title="overhead_pct")
    return fig


def make_stage_stacked_figure(rows: list[dict[str, Any]], value_field: str = "value_us"):
    import plotly.express as px  # type: ignore

    if not rows:
        return None
    if value_field not in {"value_us", "value_pct"}:
        value_field = "value_us"
    x = [f"{r['scenario']}/{r['mode']}/{r['phase']}" for r in rows]
    y_title = "time_us" if value_field == "value_us" else "percent(%)"
    fig = px.bar(
        rows,
        x=x,
        y=value_field,
        color="component",
        title="Stage Time Stacked",
    )
    fig.update_layout(template="plotly_white", xaxis_title="scenario/mode/phase", yaxis_title=y_title, barmode="stack")
    return fig


def make_pareto_figure(rows: list[dict[str, Any]]):
    import plotly.express as px  # type: ignore

    if not rows:
        return None
    fig = px.scatter(
        rows,
        x="latency_ms",
        y="throughput",
        color="mode",
        symbol="scenario",
        size="samples",
        hover_data=["phase"],
        title="Pareto: Throughput vs Latency",
    )
    fig.update_layout(template="plotly_white", xaxis_title="latency_ms", yaxis_title="throughput")
    return fig


def make_component_share_figure(rows: list[dict[str, Any]]):
    import plotly.express as px  # type: ignore

    if not rows:
        return None
    fig = px.pie(
        rows,
        names="component",
        values="value_us",
        hole=0.5,
        title="Component Composition (Donut)",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(template="plotly_white", showlegend=False)
    return fig


def make_mode_metric_figure(rows: list[dict[str, Any]], metric: str):
    import plotly.express as px  # type: ignore

    if not rows:
        return None
    allowed = {
        "avg_runner_duration_sec": "Average Runner Duration (s)",
        "avg_throughput": "Average Throughput",
        "avg_latency_ms": "Average Latency (ms)",
        "avg_gpu_util_proxy": "Average GPU Util Proxy",
    }
    if metric not in allowed:
        metric = "avg_throughput"

    plot_rows = [r for r in rows if to_float(r.get(metric)) is not None]
    if not plot_rows:
        return None
    fig = px.bar(
        plot_rows,
        x="mode",
        y=metric,
        color="scenario",
        barmode="group",
        text=metric,
        title=f"Mode Summary: {allowed[metric]}",
    )
    fig.update_traces(texttemplate="%{text:.3g}", textposition="outside")
    fig.update_layout(template="plotly_white", xaxis_title="mode", yaxis_title=allowed[metric])
    return fig
