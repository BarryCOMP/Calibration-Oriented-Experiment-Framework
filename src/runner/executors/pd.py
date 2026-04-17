from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..artifacts import CasePaths, prepare_case_paths
from ..config_schema import ExperimentConfig
from ..types import CaseResult, CaseSpec, RunLayout


def _wait_ready(base_url: str, timeout_sec: int) -> None:
    endpoints = [f"{base_url}/health", f"{base_url}/v1/models"]
    start = time.time()
    while True:
        for endpoint in endpoints:
            try:
                with urlopen(endpoint, timeout=3) as resp:  # nosec B310
                    if resp.status == 200:
                        return
            except URLError:
                pass
            except Exception:
                pass
        if time.time() - start > timeout_sec:
            raise TimeoutError(f"Server not ready: {base_url}")
        time.sleep(1)


def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    req = Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=20) as resp:  # nosec B310
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _terminate_process(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=15)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


def _start_process(
    cmd: list[str],
    env: dict[str, str],
    cwd: Path,
    log_path: Path,
) -> tuple[subprocess.Popen[Any], Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(  # nosec B603
        cmd,
        stdout=handle,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=env,
        start_new_session=(os.name != "nt"),
    )
    return proc, handle


def _dataset_args(params: dict[str, Any]) -> list[str]:
    dataset_name = str(params.get("dataset_name", "random"))
    args = ["--dataset-name", dataset_name, "--num-prompts", str(params.get("num_prompts", 100))]
    if dataset_name == "random":
        args += [
            "--random-input-len",
            str(params.get("random_input_len", 256)),
            "--random-output-len",
            str(params.get("random_output_len", 128)),
            "--random-range-ratio",
            str(params.get("random_range_ratio", 0.0)),
        ]
    elif dataset_name == "sharegpt":
        if "dataset_path" in params and str(params["dataset_path"]).strip():
            args += ["--dataset-path", str(params["dataset_path"])]
        args += ["--sharegpt-output-len", str(params.get("sharegpt_output_len", 512))]
    return args


def _wrap_nsys(
    cmd: list[str],
    config: ExperimentConfig,
    output_prefix: Path,
    capture_range: bool,
) -> list[str]:
    out = [
        config.global_config.nsys_bin,
        "profile",
        "--trace-fork-before-exec=true",
        "--cuda-graph-trace=node",
        f"--trace={config.profiling.nsys.trace}",
        f"--sample={config.profiling.nsys.sample}",
        f"--cpuctxsw={config.profiling.nsys.cpuctxsw}",
        "--force-overwrite=true",
        "-o",
        str(output_prefix),
    ]
    if capture_range:
        out += ["--capture-range=cudaProfilerApi", "--capture-range-end=stop"]
    if config.profiling.nsys.delay_sec > 0:
        out += ["--delay", str(config.profiling.nsys.delay_sec)]
    if config.profiling.nsys.duration_sec > 0:
        out += ["--duration", str(config.profiling.nsys.duration_sec)]
    return out + cmd


def _pd_nsys_mode_flags(mode: str) -> tuple[bool, bool]:
    # Keep backward compatibility: `nsys` means profile both server roles.
    if mode == "nsys":
        return True, True
    if mode == "nsys_prefill":
        return True, False
    if mode == "nsys_decode":
        return False, True
    return False, False


def run_case(
    config: ExperimentConfig,
    layout: RunLayout,
    case: CaseSpec,
    dry_run: bool,
    timeout_sec: int,
    workdir: Path,
) -> CaseResult:
    paths = prepare_case_paths(layout, case.case_id)
    params = case.params
    scenario = str(params.get("scenario", "pd"))
    mode = str(params.get("mode", "baseline"))
    if mode == "torch":
        mode = "torch_prefill"
    nsys_prefill_enabled, nsys_decode_enabled = _pd_nsys_mode_flags(mode)
    nsys_mode = nsys_prefill_enabled or nsys_decode_enabled

    host = str(params.get("pd_host", "127.0.0.1"))
    prefill_port = int(params.get("pd_prefill_port", 30000))
    decode_port = int(params.get("pd_decode_port", 30001))
    router_port = int(params.get("pd_router_port", 8000))

    prefill_base = f"http://{host}:{prefill_port}"
    decode_base = f"http://{host}:{decode_port}"
    router_base = f"http://{host}:{router_port}"

    g = config.global_config
    start = time.time()

    disable_radix = bool(params.get("pd_disable_radix_cache", True))
    disable_cudagraph = bool(params.get("pd_disable_cuda_graph", True))
    disagg_backend = str(params.get("pd_disaggregation_transfer_backend", "mooncake"))
    ib_device = str(params.get("pd_disaggregation_ib_device", "")).strip()

    prefill_cmd = [
        g.python_bin,
        "-m",
        "sglang.launch_server",
        "--model-path",
        g.model_path,
        "--host",
        host,
        "--port",
        str(prefill_port),
        "--disaggregation-mode",
        "prefill",
        "--disaggregation-transfer-backend",
        disagg_backend,
    ]
    decode_cmd = [
        g.python_bin,
        "-m",
        "sglang.launch_server",
        "--model-path",
        g.model_path,
        "--host",
        host,
        "--port",
        str(decode_port),
        "--disaggregation-mode",
        "decode",
        "--disaggregation-transfer-backend",
        disagg_backend,
    ]
    if g.tokenizer_path:
        prefill_cmd += ["--tokenizer-path", g.tokenizer_path]
        decode_cmd += ["--tokenizer-path", g.tokenizer_path]
    if ib_device:
        prefill_cmd += ["--disaggregation-ib-device", ib_device]
        decode_cmd += ["--disaggregation-ib-device", ib_device]
    decode_base_gpu = str(params.get("pd_decode_base_gpu_id", "")).strip()
    if decode_base_gpu:
        decode_cmd += ["--base-gpu-id", decode_base_gpu]
    if disable_radix:
        prefill_cmd += ["--disable-radix-cache"]
        decode_cmd += ["--disable-radix-cache"]
    if disable_cudagraph:
        prefill_cmd += ["--disable-cuda-graph"]
        decode_cmd += ["--disable-cuda-graph"]

    router_cmd = [
        g.python_bin,
        "-m",
        "sglang_router.launch_router",
        "--pd-disaggregation",
        "--prefill",
        prefill_base,
        "--decode",
        decode_base,
        "--host",
        host,
        "--port",
        str(router_port),
    ]

    prefill_env = os.environ.copy()
    decode_env = os.environ.copy()
    router_env = os.environ.copy()
    bench_env = os.environ.copy()
    for env in (prefill_env, decode_env, router_env, bench_env):
        env["SGLANG_USE_MODELSCOPE"] = "true" if g.use_modelscope else "false"

    prefill_cuda = str(params.get("pd_prefill_cuda_devices", "0")).strip()
    decode_cuda = str(params.get("pd_decode_cuda_devices", "1")).strip()
    if prefill_cuda:
        prefill_env["CUDA_VISIBLE_DEVICES"] = prefill_cuda
    if decode_cuda:
        decode_env["CUDA_VISIBLE_DEVICES"] = decode_cuda

    if mode in ("torch_prefill", "torch_decode"):
        trace_root = paths.traces_dir / "torch"
        trace_root.mkdir(parents=True, exist_ok=True)
        for env in (prefill_env, decode_env, bench_env):
            env["SGLANG_TORCH_PROFILER_DIR"] = str(trace_root)

    if nsys_mode:
        if nsys_prefill_enabled:
            prefill_cmd = _wrap_nsys(
                prefill_cmd,
                config=config,
                output_prefix=paths.traces_dir / "nsys_prefill_server",
                capture_range=bool(params.get("pd_nsys_capture_range", True)),
            )
        if nsys_decode_enabled:
            decode_cmd = _wrap_nsys(
                decode_cmd,
                config=config,
                output_prefix=paths.traces_dir / "nsys_decode_server",
                capture_range=bool(params.get("pd_nsys_capture_range", True)),
            )

    bench_cmd = [
        g.python_bin,
        "-m",
        "sglang.bench_serving",
        "--backend",
        "sglang",
        "--base-url",
        router_base,
        "--model",
        g.model_path,
        "--tokenizer",
        g.tokenizer_path or g.model_path,
        "--output-file",
        str(paths.result_file),
        "--seed",
        str(params.get("case_seed", 1)),
        "--warmup-requests",
        str(params.get("pd_warmup_requests", 1)),
        "--request-rate",
        str(params.get("pd_request_rate", float("inf"))),
    ]
    if params.get("pd_max_concurrency", None) is not None:
        bench_cmd += ["--max-concurrency", str(params["pd_max_concurrency"])]
    bench_cmd += _dataset_args(params)

    if mode == "torch_prefill":
        bench_cmd += [
            "--profile",
            "--profile-activities",
            *config.profiling.torch.activities,
            "--profile-start-step",
            str(config.profiling.torch.start_step),
            "--profile-steps",
            str(config.profiling.torch.steps),
            "--pd-separated",
            "--profile-prefill-url",
            prefill_base,
        ]
    elif mode == "torch_decode":
        bench_cmd += [
            "--profile",
            "--profile-activities",
            *config.profiling.torch.activities,
            "--profile-start-step",
            str(config.profiling.torch.start_step),
            "--profile-steps",
            str(config.profiling.torch.steps),
            "--pd-separated",
            "--profile-decode-url",
            decode_base,
        ]

    result = CaseResult(
        case_id=case.case_id,
        scenario=scenario,
        mode=mode,
        status="dry_run" if dry_run else "running",
        attempt=1,
        command=bench_cmd,
        log_path=str(paths.log_file),
        result_path=str(paths.result_file),
        trace_path=str(paths.traces_dir),
        started_at_epoch=start,
    )
    if dry_run:
        result.ended_at_epoch = time.time()
        result.duration_sec = result.ended_at_epoch - start
        result.notes = (
            "PD commands prepared only (dry-run). "
            f"prefill_cmd={prefill_cmd} decode_cmd={decode_cmd} router_cmd={router_cmd}"
        )
        return result

    procs: list[subprocess.Popen[Any]] = []
    handles: list[Any] = []
    try:
        p_proc, p_h = _start_process(prefill_cmd, prefill_env, workdir, paths.logs_dir / "prefill_server.log")
        d_proc, d_h = _start_process(decode_cmd, decode_env, workdir, paths.logs_dir / "decode_server.log")
        procs += [p_proc, d_proc]
        handles += [p_h, d_h]

        _wait_ready(prefill_base, timeout_sec)
        _wait_ready(decode_base, timeout_sec)

        r_proc, r_h = _start_process(router_cmd, router_env, workdir, paths.logs_dir / "router.log")
        procs.append(r_proc)
        handles.append(r_h)
        time.sleep(2)

        if nsys_mode and bool(params.get("pd_nsys_capture_range", True)):
            start_step = int(params.get("pd_nsys_trigger_start_step", config.profiling.torch.start_step))
            steps = int(params.get("pd_nsys_trigger_steps", config.profiling.torch.steps))
            if nsys_prefill_enabled:
                _post_json(
                    f"{prefill_base}/start_profile",
                    {
                        "activities": ["CUDA_PROFILER"],
                        "start_step": str(start_step),
                        "num_steps": str(steps),
                        "output_dir": str(paths.traces_dir / "nsys_trigger_prefill"),
                        "profile_prefix": f"{case.case_id}_prefill",
                    },
                )
            if nsys_decode_enabled:
                _post_json(
                    f"{decode_base}/start_profile",
                    {
                        "activities": ["CUDA_PROFILER"],
                        "start_step": str(start_step),
                        "num_steps": str(steps),
                        "output_dir": str(paths.traces_dir / "nsys_trigger_decode"),
                        "profile_prefix": f"{case.case_id}_decode",
                    },
                )

        with paths.log_file.open("w", encoding="utf-8") as run_log:
            proc = subprocess.run(  # nosec B603
                bench_cmd,
                stdout=run_log,
                stderr=subprocess.STDOUT,
                cwd=workdir,
                env=bench_env,
                timeout=timeout_sec,
                check=False,
            )

        result.ended_at_epoch = time.time()
        result.duration_sec = result.ended_at_epoch - start
        if proc.returncode == 0:
            result.status = "success"
            return result
        result.status = "failed"
        result.error = f"Bench command exited with code {proc.returncode}"
        return result
    except Exception as e:  # noqa: BLE001
        result.ended_at_epoch = time.time()
        result.duration_sec = result.ended_at_epoch - start
        result.status = "failed"
        result.error = f"{type(e).__name__}: {e}"
        return result
    finally:
        for proc in reversed(procs):
            _terminate_process(proc)
        for h in handles:
            try:
                h.close()
            except Exception:
                pass
