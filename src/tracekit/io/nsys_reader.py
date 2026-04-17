from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NsysEvent:
    name: str
    ts_us: float
    dur_us: float
    device: str = "unknown"
    stream_id: str = "unknown"
    rank: int = 0
    corr_id: str | None = None
    raw_category: str | None = None


@dataclass(frozen=True)
class NsysTrace:
    path: Path
    events: list[NsysEvent]
    metadata: dict[str, Any]


def discover_nsys_files(input_root: Path) -> list[Path]:
    out: list[Path] = []
    patterns = [
        "*nsys*.json",
        "*nsys*.csv",
        "*nsys*.sqlite",
        "*nsys*.sqlite3",
        "nsys_events.json",
        "nsys_events.csv",
        "nsys_events.sqlite",
        "nsys_events.sqlite3",
    ]
    for pat in patterns:
        out.extend(input_root.rglob(pat))
    filtered = [p.resolve() for p in out if p.suffix.lower() in {".json", ".csv", ".sqlite", ".sqlite3"}]
    return sorted(set(filtered))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _pick(row: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default


def _normalize_time_to_us(value: float, unit_hint: str | None) -> float:
    hint = (unit_hint or "").lower()
    if "ns" in hint:
        return value / 1000.0
    if "ms" in hint:
        return value * 1000.0
    return value


def _row_to_event(row: dict[str, Any]) -> NsysEvent | None:
    name = str(_pick(row, ["op_name", "name", "Name", "kernel_name", "Kernel Name"], "unknown"))

    ts_raw = _pick(
        row,
        ["ts_us", "start_us", "timestamp_us", "ts", "start", "Start (us)", "Start (ns)", "Start"],
        0,
    )
    dur_raw = _pick(
        row,
        ["dur_us", "duration_us", "dur", "duration", "Duration (us)", "Duration (ns)", "Duration"],
        None,
    )
    end_raw = _pick(row, ["end_us", "end", "End (us)", "End (ns)", "End"], None)
    unit_hint = str(_pick(row, ["time_unit", "unit", "Time Unit"], "") or "")
    if not unit_hint:
        if any(k in row for k in ("Start (ns)", "Duration (ns)", "End (ns)")):
            unit_hint = "ns"

    ts = _normalize_time_to_us(_as_float(ts_raw, 0.0), unit_hint)
    if dur_raw is not None:
        dur = _normalize_time_to_us(_as_float(dur_raw, 0.0), unit_hint)
    elif end_raw is not None:
        end_us = _normalize_time_to_us(_as_float(end_raw, ts), unit_hint)
        dur = max(0.0, end_us - ts)
    else:
        dur = 0.0

    if ts == 0.0 and dur == 0.0 and name == "unknown":
        return None

    return NsysEvent(
        name=name,
        ts_us=ts,
        dur_us=max(0.0, dur),
        device=str(_pick(row, ["device", "device_id", "Device"], "unknown")),
        stream_id=str(_pick(row, ["stream_id", "stream", "Strm", "Stream"], "unknown")),
        rank=_as_int(_pick(row, ["rank", "Rank"], 0), 0),
        corr_id=str(_pick(row, ["corr_id", "correlation_id", "Correlation ID"], "")) or None,
        raw_category=str(_pick(row, ["category", "cat", "Category"], "")) or None,
    )


def _read_json_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    metadata: dict[str, Any] = {}
    if isinstance(data, list):
        rows = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        if isinstance(data.get("events"), list):
            rows = [x for x in data["events"] if isinstance(x, dict)]
        elif isinstance(data.get("traceEvents"), list):
            rows = [x for x in data["traceEvents"] if isinstance(x, dict)]
        else:
            rows = [data]
        metadata = {k: v for k, v in data.items() if k not in {"events", "traceEvents"}}
    else:
        rows = []
    return rows, metadata


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _quote_ident(name: str) -> str:
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({_quote_ident(table)})")
    rows = cur.fetchall()
    return [str(r[1]) for r in rows if len(r) > 1]


def _pick_col(columns: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in columns:
            return c
    return None


def _infer_sqlite_time_unit(
    conn: sqlite3.Connection,
    table: str,
    start_col: str,
    dur_col: str | None,
    end_col: str | None,
) -> str:
    # Explicit suffix hints are always preferred.
    if any(start_col.endswith(x) for x in ("Ns", "_ns")):
        return "ns"
    if dur_col and any(dur_col.endswith(x) for x in ("Ns", "_ns")):
        return "ns"
    if end_col and any(end_col.endswith(x) for x in ("Ns", "_ns")):
        return "ns"

    # Heuristic for nsys sqlite exports:
    # many tables use generic start/end column names but values are nanoseconds.
    # We sample one non-zero row and infer by magnitude.
    select_cols = [start_col]
    if dur_col:
        select_cols.append(dur_col)
    elif end_col:
        select_cols.append(end_col)

    sql = (
        "SELECT "
        + ", ".join(_quote_ident(c) for c in select_cols)
        + f" FROM {_quote_ident(table)} "
        + f"WHERE {_quote_ident(start_col)} IS NOT NULL "
        + f"LIMIT 1"
    )
    try:
        row = conn.execute(sql).fetchone()
    except Exception:
        return "us"
    if not row:
        return "us"

    start_val = abs(_as_float(row[0], 0.0))
    second_val = abs(_as_float(row[1], 0.0)) if len(row) > 1 else 0.0

    # Typical start in us is around <=1e8 for short traces;
    # ns is often >=1e9. Durations in ns commonly exceed 1e6.
    if start_val >= 1e9 or second_val >= 1e6:
        return "ns"
    return "us"


def _select_sqlite_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conn = sqlite3.connect(str(path))
    try:
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = [str(r[0]) for r in table_rows if r and r[0]]
        out_rows: list[dict[str, Any]] = []

        for table in tables:
            cols = _table_columns(conn, table)
            if not cols:
                continue
            colset = set(cols)

            name_col = _pick_col(colset, ["name", "Name", "kernel_name", "Kernel Name", "demangledName", "shortName"])
            start_col = _pick_col(colset, ["start_us", "start", "ts_us", "ts", "startNs", "start_ns"])
            dur_col = _pick_col(colset, ["duration_us", "dur_us", "duration", "dur", "durationNs", "duration_ns"])
            end_col = _pick_col(colset, ["end_us", "end", "endNs", "end_ns"])
            if start_col is None or (dur_col is None and end_col is None):
                continue

            device_col = _pick_col(colset, ["device", "device_id", "deviceId", "Device"])
            stream_col = _pick_col(colset, ["stream_id", "stream", "streamId", "Stream"])
            corr_col = _pick_col(colset, ["corr_id", "correlation_id", "correlationId", "Correlation ID"])
            rank_col = _pick_col(colset, ["rank", "Rank"])

            unit_hint = _infer_sqlite_time_unit(
                conn=conn,
                table=table,
                start_col=start_col,
                dur_col=dur_col,
                end_col=end_col,
            )

            name_expr = _quote_ident(name_col) if name_col else f"'{table}'"
            start_expr = _quote_ident(start_col)
            if dur_col:
                dur_expr = _quote_ident(dur_col)
            else:
                assert end_col is not None
                dur_expr = f"({_quote_ident(end_col)} - {_quote_ident(start_col)})"

            device_expr = _quote_ident(device_col) if device_col else "'unknown'"
            stream_expr = _quote_ident(stream_col) if stream_col else "'unknown'"
            corr_expr = _quote_ident(corr_col) if corr_col else "NULL"
            rank_expr = _quote_ident(rank_col) if rank_col else "0"

            sql = (
                "SELECT "
                f"{name_expr} AS name, "
                f"{start_expr} AS ts, "
                f"{dur_expr} AS dur, "
                f"{device_expr} AS device, "
                f"{stream_expr} AS stream_id, "
                f"{corr_expr} AS corr_id, "
                f"{rank_expr} AS rank "
                f"FROM {_quote_ident(table)}"
            )
            try:
                cur = conn.execute(sql)
            except Exception:
                continue
            fetched = cur.fetchall()
            for r in fetched:
                out_rows.append(
                    {
                        "name": r[0],
                        "ts": r[1],
                        "dur": r[2],
                        "device": r[3],
                        "stream_id": r[4],
                        "corr_id": r[5],
                        "rank": r[6],
                        "category": table,
                        "time_unit": unit_hint,
                    }
                )

        meta = {"tables": tables}
        return out_rows, meta
    finally:
        conn.close()


def read_nsys_trace(path: Path) -> NsysTrace:
    if path.suffix.lower() == ".json":
        rows, metadata = _read_json_rows(path)
    elif path.suffix.lower() == ".csv":
        rows = _read_csv_rows(path)
        metadata = {}
    elif path.suffix.lower() in {".sqlite", ".sqlite3"}:
        rows, metadata = _select_sqlite_rows(path)
    else:
        raise ValueError(f"Unsupported nsys input format: {path}")

    events: list[NsysEvent] = []
    for row in rows:
        e = _row_to_event(row)
        if e is not None:
            events.append(e)
    return NsysTrace(path=path, events=events, metadata=metadata)
