from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..normalize import UnifiedEvent


def _is_kv_cache_transfer(op_name: str, category: str) -> bool:
    low = f"{op_name} {category}".lower()
    strong_markers = (
        "kvcache",
        "kv_cache",
        "kv cache",
        "store_kvcache",
        "store_kv_cache",
        "pagedkvcache",
        "paged_kv_cache",
    )
    if any(k in low for k in strong_markers):
        return True

    if "kv" not in low:
        return False

    transfer_markers = (
        "transfer",
        "send",
        "recv",
        "copy",
        "memcpy",
        "scatter",
        "gather",
        "p2p",
        "mooncake",
        "cache",
    )
    return any(k in low for k in transfer_markers)


def build_phase_metrics(events: list[UnifiedEvent]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for e in events:
        key = (e.run_id, e.scenario, e.mode, e.phase)
        row = buckets.get(key)
        if row is None:
            row = {
                "run_id": e.run_id,
                "scenario": e.scenario,
                "mode": e.mode,
                "phase": e.phase,
                "total_time_us": 0.0,
                "compute_time_us": 0.0,
                "comm_time_us": 0.0,
                "wait_time_us": 0.0,
                "scheduler_time_us": 0.0,
                "kv_cache_transfer_time_us": 0.0,
                "kv_cache_transfer_events": 0,
                "kv_cache_transfer_ratio": 0.0,
                "gpu_util_proxy": 0.0,
                "num_events": 0,
            }
            buckets[key] = row

        dur = max(0.0, float(e.dur_us))
        row["total_time_us"] += dur
        row["num_events"] += 1

        if e.category == "compute":
            row["compute_time_us"] += dur
        elif e.category == "communication":
            row["comm_time_us"] += dur
        elif e.category == "idle":
            row["wait_time_us"] += dur
        elif e.category == "scheduler":
            row["scheduler_time_us"] += dur

        if _is_kv_cache_transfer(e.op_name, e.category):
            row["kv_cache_transfer_time_us"] += dur
            row["kv_cache_transfer_events"] += 1

    out = list(buckets.values())
    for row in out:
        total = float(row["total_time_us"])
        active = float(row["compute_time_us"]) + float(row["comm_time_us"])
        row["gpu_util_proxy"] = active / total if total > 0 else 0.0
        row["kv_cache_transfer_ratio"] = (float(row["kv_cache_transfer_time_us"]) / total) if total > 0 else 0.0
    out.sort(key=lambda x: (x["run_id"], x["scenario"], x["mode"], x["phase"]))
    return out
