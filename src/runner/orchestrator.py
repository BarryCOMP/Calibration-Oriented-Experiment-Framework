from __future__ import annotations

import time
from pathlib import Path

from .artifacts import create_run_layout
from .config_schema import expand_cases, load_experiment_config
from .diagnostics import enrich_failure_with_logs
from .executors import offline as offline_executor
from .executors import pd as pd_executor
from .manifest import append_case_result, init_manifest, write_manifest
from .retry import run_with_retry
from .types import CaseResult


def _run_single_case(
    scenario: str,
    config,
    layout,
    case,
    dry_run: bool,
    workdir: Path,
) -> CaseResult:
    if scenario == "offline":
        return offline_executor.run_case(
            config=config,
            layout=layout,
            case=case,
            dry_run=dry_run,
            timeout_sec=config.constraints.timeout_sec_per_case,
            workdir=workdir,
        )
    if scenario == "pd":
        return pd_executor.run_case(
            config=config,
            layout=layout,
            case=case,
            dry_run=dry_run,
            timeout_sec=config.constraints.timeout_sec_per_case,
            workdir=workdir,
        )
    return CaseResult(
        case_id=case.case_id,
        scenario=scenario,
        mode=str(case.params.get("mode", "unknown")),
        status="failed",
        attempt=1,
        error=f"Unsupported scenario: {scenario}",
    )


def run_experiments(
    config_path: str | Path,
    dry_run: bool = False,
    continue_on_error: bool = False,
    output_root_override: str | None = None,
    run_name_override: str | None = None,
) -> Path:
    workdir = Path.cwd()
    config = load_experiment_config(config_path)

    run_name = run_name_override or config.run_name
    output_root = output_root_override or config.output_root
    layout = create_run_layout(output_root=output_root, run_name=run_name)

    manifest = init_manifest(
        config_path=str(config_path),
        layout=layout,
        config_raw=config.raw,
        dry_run=dry_run,
    )

    cases = expand_cases(config)
    manifest["total_cases"] = len(cases)
    manifest["started_at_epoch"] = time.time()
    manifest["max_parallel_cases"] = config.constraints.max_parallel_cases
    if config.constraints.max_parallel_cases != 1:
        manifest["notes"] = (
            "Phase A skeleton executes cases sequentially; "
            "max_parallel_cases is recorded but not yet enforced."
        )

    has_failure = False
    executed_cases = 0
    for idx, case in enumerate(cases, start=1):
        scenario = str(case.params.get("scenario", "")).strip()
        if not scenario:
            result = CaseResult(
                case_id=case.case_id,
                scenario="unknown",
                mode=str(case.params.get("mode", "unknown")),
                status="failed",
                attempt=1,
                error="Missing 'scenario' in case params.",
            )
            append_case_result(manifest, result)
            write_manifest(manifest, layout)
            executed_cases += 1
            has_failure = True
            if not continue_on_error:
                break
            continue

        print(f"[runner] ({idx}/{len(cases)}) case={case.case_id} scenario={scenario} mode={case.params.get('mode')}")

        last_result: CaseResult | None = None

        def _attempt():
            nonlocal last_result
            r = _run_single_case(
                scenario=scenario,
                config=config,
                layout=layout,
                case=case,
                dry_run=dry_run,
                workdir=workdir,
            )
            last_result = r
            if r.status == "failed":
                raise RuntimeError(r.error or "case failed")
            return r

        try:
            result, attempts = run_with_retry(
                func=_attempt,
                max_attempts=config.constraints.retry.max_attempts,
                backoff_sec=config.constraints.retry.backoff_sec,
                on_retry=lambda attempt, err: print(
                    f"[runner] retry case={case.case_id}, attempt={attempt + 1}, reason={err}"
                ),
            )
            result.attempt = attempts
        except Exception as e:  # noqa: BLE001
            has_failure = True
            if last_result is not None:
                result = last_result
                result.attempt = config.constraints.retry.max_attempts
                if not result.error:
                    result.error = f"{type(e).__name__}: {e}"
            else:
                result = CaseResult(
                    case_id=case.case_id,
                    scenario=scenario,
                    mode=str(case.params.get("mode", "unknown")),
                    status="failed",
                    attempt=config.constraints.retry.max_attempts,
                    error=f"{type(e).__name__}: {e}",
                )

        enrich_failure_with_logs(result)
        append_case_result(manifest, result)
        write_manifest(manifest, layout)
        executed_cases += 1

        if result.status == "failed" and not continue_on_error:
            break

    manifest["ended_at_epoch"] = time.time()
    manifest["duration_sec"] = manifest["ended_at_epoch"] - manifest["started_at_epoch"]
    manifest["has_failure"] = has_failure
    manifest["executed_cases"] = executed_cases
    manifest["stopped_early"] = executed_cases < len(cases)
    status_counts: dict[str, int] = {}
    for c in manifest["cases"]:
        st = str(c.get("status", "unknown"))
        status_counts[st] = status_counts.get(st, 0) + 1
    manifest["status_counts"] = status_counts
    manifest_path = write_manifest(manifest, layout)
    print(f"[runner] manifest saved: {manifest_path}")
    return manifest_path
