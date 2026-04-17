from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import CaseSpec


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "PyYAML is required to load ExperimentSpec YAML. "
            "Install with: pip install pyyaml"
        ) from e

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config root (expect mapping): {path}")
    return data


def _as_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"'{name}' must be a mapping/dict")
    return value


def _as_list(value: Any, name: str) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value]


def _to_int(value: Any, name: str, min_value: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError(f"'{name}' must be an integer")
    try:
        out = int(value)
    except Exception as e:
        raise ValueError(f"'{name}' must be an integer") from e
    if min_value is not None and out < min_value:
        raise ValueError(f"'{name}' must be >= {min_value}, got {out}")
    return out


@dataclass(frozen=True)
class GlobalConfig:
    model_path: str
    tokenizer_path: str | None = None
    use_modelscope: bool = True
    python_bin: str = "python3"
    nsys_bin: str = "nsys"


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 1
    backoff_sec: int = 0


@dataclass(frozen=True)
class ConstraintsConfig:
    max_parallel_cases: int = 1
    timeout_sec_per_case: int = 3600
    retry: RetryConfig = field(default_factory=RetryConfig)


@dataclass(frozen=True)
class TorchProfilingConfig:
    activities: list[str] = field(default_factory=lambda: ["GPU"])
    start_step: int = 5
    steps: int = 50


@dataclass(frozen=True)
class NsysProfilingConfig:
    trace: str = "cuda,nvtx"
    sample: str = "none"
    cpuctxsw: str = "none"
    delay_sec: int = 0
    duration_sec: int = 0


@dataclass(frozen=True)
class ProfilingConfig:
    torch: TorchProfilingConfig = field(default_factory=TorchProfilingConfig)
    nsys: NsysProfilingConfig = field(default_factory=NsysProfilingConfig)


@dataclass(frozen=True)
class MatrixConfig:
    values: dict[str, list[Any]]
    runs_per_case: int = 1


@dataclass(frozen=True)
class ExperimentConfig:
    version: str
    run_name: str
    seed: int
    output_root: str
    global_config: GlobalConfig
    matrix: MatrixConfig
    constraints: ConstraintsConfig
    profiling: ProfilingConfig
    raw: dict[str, Any]


def load_experiment_config(config_path: str | Path) -> ExperimentConfig:
    path = Path(config_path).resolve()
    data = _load_yaml(path)

    version = str(data.get("version", "v1"))
    run_name = str(data.get("run_name", "")).strip()
    output_root = str(data.get("output_root", "experiments/runs")).strip()
    seed = _to_int(data.get("seed", 1), "seed", min_value=0)

    if not run_name:
        raise ValueError("'run_name' is required")

    g_raw = _as_dict(data.get("global", {}), "global")
    model_path = str(g_raw.get("model_path", "")).strip()
    if not model_path:
        raise ValueError("'global.model_path' is required")
    tokenizer_path = g_raw.get("tokenizer_path")
    tokenizer_path = str(tokenizer_path).strip() if tokenizer_path else None
    global_cfg = GlobalConfig(
        model_path=model_path,
        tokenizer_path=tokenizer_path,
        use_modelscope=bool(g_raw.get("use_modelscope", True)),
        python_bin=str(g_raw.get("python_bin", "python3")),
        nsys_bin=str(g_raw.get("nsys_bin", "nsys")),
    )

    m_raw = _as_dict(data.get("matrix", {}), "matrix")
    runs_per_case = _to_int(m_raw.get("runs_per_case", 1), "matrix.runs_per_case", 1)
    matrix_values: dict[str, list[Any]] = {}
    for key, value in m_raw.items():
        if key == "runs_per_case":
            continue
        matrix_values[key] = _as_list(value, f"matrix.{key}")
        if not matrix_values[key]:
            raise ValueError(f"matrix.{key} cannot be empty")
    if not matrix_values:
        raise ValueError("'matrix' must contain at least one varying key")
    matrix_cfg = MatrixConfig(values=matrix_values, runs_per_case=runs_per_case)

    c_raw = _as_dict(data.get("constraints", {}), "constraints")
    retry_raw = _as_dict(c_raw.get("retry", {}), "constraints.retry")
    retry_cfg = RetryConfig(
        max_attempts=_to_int(retry_raw.get("max_attempts", 1), "constraints.retry.max_attempts", 1),
        backoff_sec=_to_int(retry_raw.get("backoff_sec", 0), "constraints.retry.backoff_sec", 0),
    )
    constraints_cfg = ConstraintsConfig(
        max_parallel_cases=_to_int(c_raw.get("max_parallel_cases", 1), "constraints.max_parallel_cases", 1),
        timeout_sec_per_case=_to_int(c_raw.get("timeout_sec_per_case", 3600), "constraints.timeout_sec_per_case", 1),
        retry=retry_cfg,
    )

    p_raw = _as_dict(data.get("profiling", {}), "profiling")
    torch_raw = _as_dict(p_raw.get("torch", {}), "profiling.torch")
    nsys_raw = _as_dict(p_raw.get("nsys", {}), "profiling.nsys")
    profiling_cfg = ProfilingConfig(
        torch=TorchProfilingConfig(
            activities=[str(x) for x in _as_list(torch_raw.get("activities", ["GPU"]), "profiling.torch.activities")],
            start_step=_to_int(torch_raw.get("start_step", 5), "profiling.torch.start_step", 0),
            steps=_to_int(torch_raw.get("steps", 50), "profiling.torch.steps", 1),
        ),
        nsys=NsysProfilingConfig(
            trace=str(nsys_raw.get("trace", "cuda,nvtx")),
            sample=str(nsys_raw.get("sample", "none")),
            cpuctxsw=str(nsys_raw.get("cpuctxsw", "none")),
            delay_sec=_to_int(nsys_raw.get("delay_sec", 0), "profiling.nsys.delay_sec", 0),
            duration_sec=_to_int(nsys_raw.get("duration_sec", 0), "profiling.nsys.duration_sec", 0),
        ),
    )

    return ExperimentConfig(
        version=version,
        run_name=run_name,
        seed=seed,
        output_root=output_root,
        global_config=global_cfg,
        matrix=matrix_cfg,
        constraints=constraints_cfg,
        profiling=profiling_cfg,
        raw=data,
    )


def expand_cases(config: ExperimentConfig) -> list[CaseSpec]:
    def _expand_mode_variants(params: dict[str, Any]) -> list[str]:
        scenario = str(params.get("scenario", "unknown"))
        mode = str(params.get("mode", "unknown"))
        if scenario != "pd":
            return [mode]
        if mode == "torch":
            return ["torch_prefill", "torch_decode"]
        if mode == "nsys":
            compare_mode = str(params.get("pd_nsys_compare_mode", "split"))
            if compare_mode == "both":
                return ["nsys"]
            return ["nsys_prefill", "nsys_decode"]
        return [mode]

    keys = list(config.matrix.values.keys())
    value_lists = [config.matrix.values[k] for k in keys]
    cases: list[CaseSpec] = []
    case_idx = 0
    for combo in itertools.product(*value_lists):
        params = dict(zip(keys, combo))
        for expanded_mode in _expand_mode_variants(params):
            for run_index in range(1, config.matrix.runs_per_case + 1):
                case_idx += 1
                scenario = str(params.get("scenario", "unknown"))
                case_id = f"{case_idx:04d}_{scenario}_{expanded_mode}_r{run_index}"
                seeded_params = dict(params)
                seeded_params["mode"] = expanded_mode
                seeded_params["case_seed"] = config.seed + case_idx * 100 + run_index
                cases.append(CaseSpec(case_id=case_id, run_index=run_index, params=seeded_params))
    return cases
