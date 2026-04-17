from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from ..artifacts import CasePaths, prepare_case_paths
from ..config_schema import ExperimentConfig
from ..types import CaseResult, CaseSpec, RunLayout


def _append_dataset_args(cmd: list[str], params: dict[str, Any]) -> None:
    dataset_name = str(params.get("dataset_name", "random"))
    cmd += ["--dataset-name", dataset_name]
    cmd += ["--num-prompts", str(params.get("num_prompts", 20))]

    if dataset_name == "random":
        cmd += [
            "--random-input-len",
            str(params.get("random_input_len", 256)),
            "--random-output-len",
            str(params.get("random_output_len", 128)),
            "--random-range-ratio",
            str(params.get("random_range_ratio", 0.0)),
        ]
    elif dataset_name == "sharegpt":
        if "dataset_path" in params and str(params["dataset_path"]).strip():
            cmd += ["--dataset-path", str(params["dataset_path"])]
        cmd += ["--sharegpt-output-len", str(params.get("sharegpt_output_len", 512))]


def _build_offline_cmd(
    config: ExperimentConfig,
    case: CaseSpec,
    paths: CasePaths,
    trace_path: Path,
) -> tuple[list[str], dict[str, str]]:
    params = case.params
    mode = str(params.get("mode", "baseline"))
    g = config.global_config
    env: dict[str, str] = {}

    app_cmd = [
        g.python_bin,
        "-m",
        "sglang.bench_offline_throughput",
        "--backend",
        "engine",
        "--model-path",
        g.model_path,
        "--result-filename",
        str(paths.result_file),
        "--seed",
        str(params.get("case_seed", 1)),
        "--log-level",
        str(params.get("log_level", "info")),
        "--mem-fraction-static",
        str(params.get("mem_fraction_static", 0.9)),
    ]
    if g.tokenizer_path:
        app_cmd += ["--tokenizer-path", g.tokenizer_path]

    _append_dataset_args(app_cmd, params)

    if mode == "baseline":
        return app_cmd, env
    if mode == "torch":
        env["SGLANG_TORCH_PROFILER_DIR"] = str(trace_path)
        app_cmd += ["--profile"]
        return app_cmd, env
    if mode == "nsys":
        nsys_prefix = trace_path / "nsys_offline"
        nsys_cmd = [
            g.nsys_bin,
            "profile",
            "--trace-fork-before-exec=true",
            "--cuda-graph-trace=node",
            f"--trace={config.profiling.nsys.trace}",
            f"--sample={config.profiling.nsys.sample}",
            f"--cpuctxsw={config.profiling.nsys.cpuctxsw}",
            "--force-overwrite=true",
            "--output",
            str(nsys_prefix),
        ]
        if config.profiling.nsys.delay_sec > 0:
            nsys_cmd += ["--delay", str(config.profiling.nsys.delay_sec)]
        if config.profiling.nsys.duration_sec > 0:
            nsys_cmd += ["--duration", str(config.profiling.nsys.duration_sec)]
        return nsys_cmd + app_cmd, env

    raise ValueError(f"Unsupported offline mode: {mode}")


def run_case(
    config: ExperimentConfig,
    layout: RunLayout,
    case: CaseSpec,
    dry_run: bool,
    timeout_sec: int,
    workdir: Path,
) -> CaseResult:
    paths = prepare_case_paths(layout, case.case_id)
    scenario = str(case.params.get("scenario", "offline"))
    mode = str(case.params.get("mode", "baseline"))
    start = time.time()

    cmd, env_overrides = _build_offline_cmd(
        config=config,
        case=case,
        paths=paths,
        trace_path=paths.traces_dir,
    )

    result = CaseResult(
        case_id=case.case_id,
        scenario=scenario,
        mode=mode,
        status="dry_run" if dry_run else "running",
        attempt=1,
        command=cmd,
        log_path=str(paths.log_file),
        result_path=str(paths.result_file),
        trace_path=str(paths.traces_dir),
        started_at_epoch=start,
    )

    if dry_run:
        result.ended_at_epoch = time.time()
        result.duration_sec = result.ended_at_epoch - start
        result.notes = "Command prepared only (dry-run)."
        return result

    env = os.environ.copy()
    env["SGLANG_USE_MODELSCOPE"] = "true" if config.global_config.use_modelscope else "false"
    env.update(env_overrides)

    with paths.log_file.open("w", encoding="utf-8") as log_f:
        proc = subprocess.run(  # nosec B603
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=workdir,
            env=env,
            timeout=timeout_sec,
            check=False,
        )

    result.ended_at_epoch = time.time()
    result.duration_sec = result.ended_at_epoch - start
    if proc.returncode == 0:
        result.status = "success"
        return result

    result.status = "failed"
    result.error = f"Command exited with code {proc.returncode}"
    return result
