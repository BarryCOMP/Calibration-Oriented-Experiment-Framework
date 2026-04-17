from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..normalize import UnifiedEvent


def build_queue_wait_metrics(events: list[UnifiedEvent]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in events:
        key = (e.run_id, e.scenario, e.mode)
        row = buckets.get(key)
        if row is None:
            row = {
                "run_id": e.run_id,
                "scenario": e.scenario,
                "mode": e.mode,
                "total_time_us": 0.0,
                "queue_wait_time_us": 0.0,
                "scheduler_time_us": 0.0,
                "queue_wait_ratio": 0.0,
                "scheduler_ratio": 0.0,
            }
            buckets[key] = row

        dur = max(0.0, float(e.dur_us))
        row["total_time_us"] += dur

        low = e.op_name.lower()
        if "wait" in low or "queue" in low or e.category == "idle":
            row["queue_wait_time_us"] += dur
        if e.category == "scheduler":
            row["scheduler_time_us"] += dur

    out = list(buckets.values())
    for row in out:
        total = float(row["total_time_us"])
        row["queue_wait_ratio"] = (float(row["queue_wait_time_us"]) / total) if total > 0 else 0.0
        row["scheduler_ratio"] = (float(row["scheduler_time_us"]) / total) if total > 0 else 0.0
    out.sort(key=lambda x: (x["run_id"], x["scenario"], x["mode"]))
    return out
