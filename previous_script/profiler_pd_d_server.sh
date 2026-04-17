#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pd_profile_common.sh"

MODEL_PATH="${MODEL_PATH:-LLM-Research/Meta-Llama-3.1-8B-Instruct}"
DECODE_HOST="${DECODE_HOST:-0.0.0.0}"
DECODE_PORT="${DECODE_PORT:-30001}"
DECODE_CUDA_DEVICES="${DECODE_CUDA_DEVICES:-1}"

DISAGG_TRANSFER_BACKEND="${DISAGG_TRANSFER_BACKEND:-mooncake}"
DISAGG_IB_DEVICE="${DISAGG_IB_DEVICE:-}"
DECODE_BASE_GPU_ID="${DECODE_BASE_GPU_ID:-}"
DECODE_MEM_FRACTION_STATIC="${DECODE_MEM_FRACTION_STATIC:-}"
DECODE_MAX_RUNNING_REQUESTS="${DECODE_MAX_RUNNING_REQUESTS:-}"
DECODE_EXTRA_ARGS="${DECODE_EXTRA_ARGS:-}"

CMD=(
  python -m sglang.launch_server
  --model-path "${MODEL_PATH}"
  --host "${DECODE_HOST}"
  --port "${DECODE_PORT}"
  --disaggregation-mode decode
  --disaggregation-transfer-backend "${DISAGG_TRANSFER_BACKEND}"
  --disable-radix-cache
  --disable-cuda-graph
)

if [[ -n "${DISAGG_IB_DEVICE}" ]]; then
  CMD+=(--disaggregation-ib-device "${DISAGG_IB_DEVICE}")
fi

if [[ -n "${DECODE_BASE_GPU_ID}" ]]; then
  CMD+=(--base-gpu-id "${DECODE_BASE_GPU_ID}")
fi

if [[ -n "${DECODE_MEM_FRACTION_STATIC}" ]]; then
  CMD+=(--mem-fraction-static "${DECODE_MEM_FRACTION_STATIC}")
fi

if [[ -n "${DECODE_MAX_RUNNING_REQUESTS}" ]]; then
  CMD+=(--max-running-requests "${DECODE_MAX_RUNNING_REQUESTS}")
fi

if [[ -n "${DECODE_EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARR=(${DECODE_EXTRA_ARGS})
  CMD+=("${EXTRA_ARR[@]}")
fi

echo "Starting PD decode server..."
echo "Model: ${MODEL_PATH}"
echo "Endpoint: http://${DECODE_HOST}:${DECODE_PORT}"
echo "Profiler dir: ${SGLANG_TORCH_PROFILER_DIR}"
echo "Transfer backend: ${DISAGG_TRANSFER_BACKEND}"

if [[ -n "${DECODE_CUDA_DEVICES}" ]]; then
  CUDA_VISIBLE_DEVICES="${DECODE_CUDA_DEVICES}" "${CMD[@]}"
else
  "${CMD[@]}"
fi
