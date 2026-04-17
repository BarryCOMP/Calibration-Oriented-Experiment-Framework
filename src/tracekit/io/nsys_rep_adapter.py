from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NsysRepMaterializeResult:
    rep_path: Path
    output_path: Path | None
    method: str | None
    reused: bool
    error: str | None = None


def discover_nsys_rep_files(input_root: Path) -> list[Path]:
    return sorted({p.resolve() for p in input_root.rglob("*.nsys-rep")})


def _is_fresh(artifact: Path, source: Path) -> bool:
    return artifact.exists() and artifact.stat().st_mtime >= source.stat().st_mtime


def _run_subprocess(cmd: list[str], timeout_sec: int) -> None:
    subprocess.run(  # nosec B603
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec,
    )


def _export_sqlite(rep_path: Path, nsys_bin: str, timeout_sec: int) -> Path:
    sqlite_path = rep_path.with_suffix(".sqlite")
    if _is_fresh(sqlite_path, rep_path):
        return sqlite_path

    cmd = [
        nsys_bin,
        "export",
        "--type",
        "sqlite",
        "--force-overwrite",
        "true",
        "--output",
        str(sqlite_path),
        str(rep_path),
    ]
    _run_subprocess(cmd, timeout_sec=timeout_sec)

    candidates = [
        sqlite_path,
        rep_path.parent / f"{rep_path.stem}.sqlite",
        rep_path.parent / f"{rep_path.name}.sqlite",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise RuntimeError("nsys export succeeded but sqlite output not found")


def _export_cuda_gpu_trace_csv(rep_path: Path, nsys_bin: str, timeout_sec: int) -> Path:
    prefix = rep_path.parent / rep_path.name.replace(".nsys-rep", "")
    out_csv = Path(f"{prefix}_cuda_gpu_trace.csv")
    if _is_fresh(out_csv, rep_path):
        return out_csv

    cmd = [
        nsys_bin,
        "stats",
        "-r",
        "cuda_gpu_trace",
        "-f",
        "csv",
        str(rep_path),
        "-o",
        str(prefix),
    ]
    _run_subprocess(cmd, timeout_sec=timeout_sec)
    if out_csv.exists():
        return out_csv
    raise RuntimeError("nsys stats finished but csv output not found")


def materialize_nsys_rep(
    rep_path: Path,
    nsys_bin: str = "nsys",
    timeout_sec: int = 1800,
) -> NsysRepMaterializeResult:
    try:
        sqlite_target = rep_path.with_suffix(".sqlite")
        reused = _is_fresh(sqlite_target, rep_path)
        out = _export_sqlite(rep_path, nsys_bin=nsys_bin, timeout_sec=timeout_sec)
        return NsysRepMaterializeResult(
            rep_path=rep_path,
            output_path=out,
            method="export_sqlite",
            reused=reused,
        )
    except Exception as export_err:  # noqa: BLE001
        try:
            csv_target = Path(f"{rep_path.parent / rep_path.name.replace('.nsys-rep', '')}_cuda_gpu_trace.csv")
            reused = _is_fresh(csv_target, rep_path)
            out = _export_cuda_gpu_trace_csv(rep_path, nsys_bin=nsys_bin, timeout_sec=timeout_sec)
            return NsysRepMaterializeResult(
                rep_path=rep_path,
                output_path=out,
                method="stats_cuda_gpu_trace_csv",
                reused=reused,
            )
        except Exception as stats_err:  # noqa: BLE001
            return NsysRepMaterializeResult(
                rep_path=rep_path,
                output_path=None,
                method=None,
                reused=False,
                error=f"export_error={type(export_err).__name__}: {export_err}; "
                f"stats_error={type(stats_err).__name__}: {stats_err}",
            )

