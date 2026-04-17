from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from .charts import (
        build_component_share_rows,
        build_mode_summary_rows,
        build_overhead_rows,
        build_pareto_rows,
        build_stage_stacked_rows,
        build_stage_stacked_rows_relative,
        make_component_share_figure,
        make_mode_metric_figure,
        make_overhead_figure,
        make_pareto_figure,
        make_stage_stacked_figure,
    )
    from .data_loader import discover_runs, load_run_bundle
except ImportError:
    # Support direct script execution such as:
    # streamlit run src/dashboard/app.py
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.dashboard.charts import (  # type: ignore
        build_component_share_rows,
        build_mode_summary_rows,
        build_overhead_rows,
        build_pareto_rows,
        build_stage_stacked_rows,
        build_stage_stacked_rows_relative,
        make_component_share_figure,
        make_mode_metric_figure,
        make_overhead_figure,
        make_pareto_figure,
        make_stage_stacked_figure,
    )
    from src.dashboard.data_loader import discover_runs, load_run_bundle  # type: ignore


def _parse_dashboard_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--runs-root", default="experiments/runs")
    parser.add_argument("--default-run-id", default=None)
    args, _ = parser.parse_known_args()
    return args


def _unique_values(rows: list[dict[str, Any]], key: str) -> list[str]:
    vals = sorted({str(r.get(key, "unknown")) for r in rows if isinstance(r, dict)})
    return vals


def main() -> None:
    import streamlit as st  # type: ignore

    args = _parse_dashboard_args()
    runs_root = Path(args.runs_root).resolve()
    st.set_page_config(page_title="LLM Serving Dashboard", layout="wide")
    st.title("LLM Serving Analysis Dashboard")
    st.caption(f"runs_root: {runs_root}")

    runs = discover_runs(runs_root)
    if not runs:
        st.warning("No runs found.")
        st.stop()

    run_id_list = [str(r["run_id"]) for r in runs]
    default_idx = 0
    if args.default_run_id and args.default_run_id in run_id_list:
        default_idx = run_id_list.index(args.default_run_id)

    chosen_run_id = st.sidebar.selectbox("Run ID", run_id_list, index=default_idx)
    chosen = next(r for r in runs if str(r["run_id"]) == chosen_run_id)
    bundle = load_run_bundle(Path(chosen["run_root"]))

    cal_rows = bundle.get("calibration_rows", [])
    if not isinstance(cal_rows, list):
        cal_rows = []

    scenarios = _unique_values(cal_rows, "scenario")
    modes = _unique_values(cal_rows, "mode")
    phases = _unique_values(cal_rows, "phase")

    sel_scenarios = st.sidebar.multiselect("Scenario", scenarios, default=scenarios)
    sel_modes = st.sidebar.multiselect("Mode", modes, default=modes)
    sel_phases = st.sidebar.multiselect("Phase", phases, default=phases)

    scenario_set = set(sel_scenarios)
    mode_set = set(sel_modes)
    phase_set = set(sel_phases)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Cases", int(chosen.get("total_cases", 0)))
    c2.metric("Executed Cases", int(chosen.get("executed_cases", 0)))
    c3.metric("Dry Run", str(bool(chosen.get("dry_run", False))))
    c4.metric("Has Failure", str(bool(chosen.get("has_failure", False))))

    st.subheader("Overhead Curve")
    overhead_rows = build_overhead_rows(
        bundle,
        scenarios=scenario_set,
        modes=mode_set,
        phases=phase_set,
    )
    try:
        fig = make_overhead_figure(overhead_rows)
    except Exception:
        fig = None
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.dataframe(overhead_rows, use_container_width=True)
    if len(overhead_rows) <= 4:
        st.caption("Current overhead samples are sparse, so this chart is shown in grouped-bar mode for readability.")

    st.subheader("Stage Time Stacked")
    stage_view = st.radio(
        "Stage View",
        options=["Relative (%)", "Absolute (us)"],
        horizontal=True,
        index=0,
    )
    if stage_view == "Relative (%)":
        stacked_rows = build_stage_stacked_rows_relative(
            cal_rows,
            scenarios=scenario_set,
            modes=mode_set,
            phases=phase_set,
        )
        stage_value_field = "value_pct"
    else:
        stacked_rows = build_stage_stacked_rows(
            cal_rows,
            scenarios=scenario_set,
            modes=mode_set,
            phases=phase_set,
        )
        stage_value_field = "value_us"
    try:
        fig2 = make_stage_stacked_figure(stacked_rows, value_field=stage_value_field)
    except Exception:
        fig2 = None
    if fig2 is not None:
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.dataframe(stacked_rows, use_container_width=True)

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Component Composition")
        comp_rows = build_component_share_rows(
            cal_rows,
            scenarios=scenario_set,
            modes=mode_set,
            phases=phase_set,
        )
        try:
            fig_comp = make_component_share_figure(comp_rows)
        except Exception:
            fig_comp = None
        if fig_comp is not None:
            st.plotly_chart(fig_comp, use_container_width=True)
        else:
            st.dataframe(comp_rows, use_container_width=True)

    with col_right:
        st.subheader("Mode Summary")
        mode_rows = build_mode_summary_rows(
            cal_rows,
            scenarios=scenario_set,
            modes=mode_set,
            phases=phase_set,
        )
        metric_options = {
            "avg_throughput": "Throughput",
            "avg_latency_ms": "Latency",
            "avg_runner_duration_sec": "Runner Duration",
            "avg_gpu_util_proxy": "GPU Util Proxy",
        }
        mode_metric = st.selectbox(
            "Summary Metric",
            options=list(metric_options.keys()),
            format_func=lambda x: metric_options[x],
            index=0,
        )
        try:
            fig_mode = make_mode_metric_figure(mode_rows, mode_metric)
        except Exception:
            fig_mode = None
        if fig_mode is not None:
            st.plotly_chart(fig_mode, use_container_width=True)
        else:
            st.dataframe(mode_rows, use_container_width=True)

    st.subheader("Pareto (Throughput vs Latency)")
    pareto_rows = build_pareto_rows(
        cal_rows,
        scenarios=scenario_set,
        modes=mode_set,
        phases=phase_set,
    )
    try:
        fig3 = make_pareto_figure(pareto_rows)
    except Exception:
        fig3 = None
    if fig3 is not None:
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.dataframe(pareto_rows, use_container_width=True)

    st.caption(
        f"rows: calibration={len(cal_rows)} | overhead={len(overhead_rows)} | stage={len(stacked_rows)} | pareto={len(pareto_rows)}"
    )

    st.subheader("Regression Threshold Status")
    threshold = bundle.get("threshold_check")
    if isinstance(threshold, dict):
        st.json(
            {
                "pass": threshold.get("pass"),
                "violations": threshold.get("summary", {}).get("violations", 0),
                "thresholds_source": threshold.get("thresholds_source"),
            }
        )
    else:
        st.info("No threshold_check.json found for this run.")

    with st.expander("Raw Bundle Summary", expanded=False):
        st.json(
            {
                "run_root": bundle.get("run_root"),
                "manifest_run_id": bundle.get("manifest", {}).get("run_id"),
                "calibration_rows": len(cal_rows),
                "has_regression_compare": isinstance(bundle.get("regression_compare"), dict),
                "has_threshold_check": isinstance(bundle.get("threshold_check"), dict),
            }
        )


if __name__ == "__main__":
    main()
