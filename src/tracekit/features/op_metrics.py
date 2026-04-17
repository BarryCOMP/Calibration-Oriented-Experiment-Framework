from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..normalize import UnifiedEvent


def build_op_metrics(events: list[UnifiedEvent], top_n: int = 20) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for e in events:
        key = (e.run_id, e.scenario, e.mode, e.phase, e.op_name)
        row = grouped.get(key)
        if row is None:
            row = {
                "run_id": e.run_id,
                "scenario": e.scenario,
                "mode": e.mode,
                "phase": e.phase,
                "op_name": e.op_name,
                "category": e.category,
                "total_dur_us": 0.0,
                "count": 0,
            }
            grouped[key] = row
        row["total_dur_us"] += max(0.0, float(e.dur_us))
        row["count"] += 1

    rows = list(grouped.values())
    rows.sort(key=lambda x: x["total_dur_us"], reverse=True)
    if top_n > 0:
        rows = rows[:top_n]
    return rows
