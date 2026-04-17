#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pd_profile_common.sh"

MODEL_PATH="${MODEL_PATH:-LLM-Research/Meta-Llama-3.1-8B-Instruct}"
PREFILL_HOST="${PREFILL_HOST:-0.0.0.0}"
PREFILL_PORT="${PREFILL_PORT:-30000}"
PREFILL_CUDA_DEVICES="${PREFILL_CUDA_DEVICES:-0}"

DISAGG_TRANSFER_BACKEND="${DISAGG_TRANSFER_BACKEND:-mooncake}"
DISAGG_IB_DEVICE="${DISAGG_IB_DEVICE:-}"
PREFILL_MEM_FRACTION_STATIC="${PREFILL_MEM_FRACTION_STATIC:-}"
PREFILL_EXTRA_ARGS="${PREFILL_EXTRA_ARGS:-}"

CMD=(
  python -m sglang.launch_server
  --model-path "${MODEL_PATH}"
  --host "${PREFILL_HOST}"
  --port "${PREFILL_PORT}"
  --disaggregation-mode prefill
  --disaggregation-transfer-backend "${DISAGG_TRANSFER_BACKEND}"
  --disable-radix-cache
  --disable-cuda-graph
)

if [[ -n "${DISAGG_IB_DEVICE}" ]]; then
  CMD+=(--disaggregation-ib-device "${DISAGG_IB_DEVICE}")
fi

if [[ -n "${PREFILL_MEM_FRACTION_STATIC}" ]]; then
  CMD+=(--mem-fraction-static "${PREFILL_MEM_FRACTION_STATIC}")
fi

if [[ -n "${PREFILL_EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARR=(${PREFILL_EXTRA_ARGS})
  CMD+=("${EXTRA_ARR[@]}")
fi

echo "Starting PD prefill server..."
echo "Model: ${MODEL_PATH}"
echo "Endpoint: http://${PREFILL_HOST}:${PREFILL_PORT}"
echo "Profiler dir: ${SGLANG_TORCH_PROFILER_DIR}"
echo "Transfer backend: ${DISAGG_TRANSFER_BACKEND}"

if [[ -n "${PREFILL_CUDA_DEVICES}" ]]; then
  CUDA_VISIBLE_DEVICES="${PREFILL_CUDA_DEVICES}" "${CMD[@]}"
else
  "${CMD[@]}"
fi
