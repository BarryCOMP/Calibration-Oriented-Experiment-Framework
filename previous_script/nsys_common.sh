#!/usr/bin/env bash
# shellcheck shell=bash

COMMON_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMMON_SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Use in-tree source when available.
if [[ -d "${REPO_ROOT}/sglang/python" ]]; then
  export PYTHONPATH="${REPO_ROOT}/sglang/python:${PYTHONPATH:-}"
fi

# Enable ModelScope model-id compatibility in sglang benchmark utilities.
export SGLANG_USE_MODELSCOPE="${SGLANG_USE_MODELSCOPE:-true}"

export no_proxy="${no_proxy:-127.0.0.1,localhost,0.0.0.0}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,0.0.0.0}"

# Common nsys settings
export NSYS_OUTPUT_ROOT="${NSYS_OUTPUT_ROOT:-/tmp/sglang_nsys}"
export NSYS_TRACE="${NSYS_TRACE:-cuda,nvtx,osrt,cublas,cudnn}"
export NSYS_FORCE_OVERWRITE="${NSYS_FORCE_OVERWRITE:-true}"
