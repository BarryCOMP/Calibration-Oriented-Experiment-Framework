#!/usr/bin/env bash
# shellcheck shell=bash

COMMON_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMMON_SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Use in-tree source when available.
if [[ -d "${REPO_ROOT}/sglang/python" ]]; then
  export PYTHONPATH="${REPO_ROOT}/sglang/python:${PYTHONPATH:-}"
fi

# ModelScope model IDs are supported in sglang when this env is enabled.
# Use string "true" for maximum compatibility across sglang versions.
export SGLANG_USE_MODELSCOPE="${SGLANG_USE_MODELSCOPE:-true}"

# Torch profiler output root. bench_serving will create timestamped sub-directories.
export SGLANG_TORCH_PROFILER_DIR="${SGLANG_TORCH_PROFILER_DIR:-/tmp/sglang_pd_profile}"
mkdir -p "${SGLANG_TORCH_PROFILER_DIR}"

export no_proxy="${no_proxy:-127.0.0.1,localhost,0.0.0.0}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,0.0.0.0}"
