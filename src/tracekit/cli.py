from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .features.op_metrics import build_op_metrics
from .features.phase_metrics import build_phase_metrics
from .features.queue_wait_metrics import build_queue_wait_metrics
from .io.nsys_rep_adapter import discover_nsys_rep_files, materialize_nsys_rep
from .io.nsys_reader import discover_nsys_files, read_nsys_trace
from .io.torch_trace_reader import discover_torch_trace_files, read_torch_trace
from .normalize.context_resolver import ContextResolver
from .normalize.normalizer import normalize_nsys_events, normalize_torch_events

if TYPE_CHECKING:
    from .normalize import UnifiedEvent


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, events: list[UnifiedEvent]) -> None:
    lines = [json.dumps(e.to_dict(), ensure_ascii=False) for e in events]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_tracekit(
    input_root: str | Path,
    output_dir: str | Path,
    top_n: int = 20,
    nsys_bin: str = "nsys",
    enable_nsys_rep_export: bool = True,
) -> dict[str, Any]:
    input_path = Path(input_root).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    torch_files = discover_torch_trace_files(input_path)
    nsys_files = discover_nsys_files(input_path)
    nsys_rep_files = discover_nsys_rep_files(input_path)
    resolver = ContextResolver(input_path)
    rep_results: list[dict[str, Any]] = []

    if enable_nsys_rep_export:
        for rep in nsys_rep_files:
            r = materialize_nsys_rep(rep, nsys_bin=nsys_bin)
            rep_results.append(
                {
                    "rep_path": str(r.rep_path),
                    "output_path": str(r.output_path) if r.output_path else None,
                    "method": r.method,
                    "reused": r.reused,
                    "error": r.error,
                }
            )
            if r.output_path is not None:
                nsys_files.append(r.output_path)
    nsys_files = sorted(set(nsys_files))

    all_events: list[UnifiedEvent] = []
    skipped_files: list[str] = []

    for tf in torch_files:
        try:
            trace = read_torch_trace(tf)
            ctx = resolver.resolve(tf, source="torch", default_run_id=input_path.name)
            all_events.extend(normalize_torch_events(trace.events, ctx))
        except Exception as e:  # noqa: BLE001
            skipped_files.append(f"{tf}: {type(e).__name__}: {e}")

    for nf in nsys_files:
        try:
            trace = read_nsys_trace(nf)
            ctx = resolver.resolve(nf, source="nsys", default_run_id=input_path.name)
            all_events.extend(normalize_nsys_events(trace.events, ctx))
        except Exception as e:  # noqa: BLE001
            skipped_files.append(f"{nf}: {type(e).__name__}: {e}")

    all_events.sort(key=lambda x: (x.run_id, x.case_id, x.ts_us, x.dur_us))

    phase_metrics = build_phase_metrics(all_events)
    op_metrics = build_op_metrics(all_events, top_n=top_n)
    queue_wait_metrics = build_queue_wait_metrics(all_events)

    normalized_path = out_dir / "normalized_events.jsonl"
    phase_path = out_dir / "phase_metrics.json"
    op_path = out_dir / "op_metrics_top.json"
    queue_path = out_dir / "queue_wait_metrics.json"
    summary_path = out_dir / "summary.json"

    _write_jsonl(normalized_path, all_events)
    _write_json(phase_path, phase_metrics)
    _write_json(op_path, op_metrics)
    _write_json(queue_path, queue_wait_metrics)

    summary = {
        "input_root": str(input_path),
        "output_dir": str(out_dir),
        "num_torch_files": len(torch_files),
        "num_nsys_files": len(nsys_files),
        "num_nsys_rep_files": len(nsys_rep_files),
        "num_nsys_rep_materialized": sum(1 for r in rep_results if r.get("output_path")),
        "num_events": len(all_events),
        "manifest_case_index_size": len(resolver.by_case_id),
        "num_skipped_files": len(skipped_files),
        "skipped_files": skipped_files,
        "nsys_rep_materialization": rep_results,
        "kv_cache_transfer_total_time_us": sum(float(r.get("kv_cache_transfer_time_us", 0.0) or 0.0) for r in phase_metrics),
        "kv_cache_transfer_total_events": sum(int(r.get("kv_cache_transfer_events", 0) or 0) for r in phase_metrics),
        "kv_cache_transfer_ratio": 0.0,
        "artifacts": {
            "normalized_events": str(normalized_path),
            "phase_metrics": str(phase_path),
            "op_metrics_top": str(op_path),
            "queue_wait_metrics": str(queue_path),
        },
    }
    total_phase_time = sum(float(r.get("total_time_us", 0.0) or 0.0) for r in phase_metrics)
    if total_phase_time > 0:
        summary["kv_cache_transfer_ratio"] = float(summary["kv_cache_transfer_total_time_us"]) / total_phase_time
    _write_json(summary_path, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TraceKit: normalize torch/nsys trace files")
    p.add_argument("--input", required=True, help="Input root directory (run root or traces root)")
    p.add_argument("--output", required=True, help="Output directory for normalized artifacts")
    p.add_argument("--top-n", type=int, default=20, help="Top-N ops by duration")
    p.add_argument("--nsys-bin", default="nsys", help="Path to nsys binary")
    p.add_argument(
        "--disable-nsys-rep-export",
        action="store_true",
        help="Disable auto materialization for *.nsys-rep",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run_tracekit(
        input_root=args.input,
        output_dir=args.output,
        top_n=args.top_n,
        nsys_bin=args.nsys_bin,
        enable_nsys_rep_export=not args.disable_nsys_rep_export,
    )
    print(f"[tracekit] done: {summary['artifacts']['normalized_events']}")
    print(f"[tracekit] files: torch={summary['num_torch_files']} nsys={summary['num_nsys_files']}")
    print(f"[tracekit] events: {summary['num_events']} skipped_files={summary['num_skipped_files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
