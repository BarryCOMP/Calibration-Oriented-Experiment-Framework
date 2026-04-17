#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/nsys_common.sh"

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

NSYS_BASENAME="${NSYS_BASENAME:-pd_decode_server}"
NSYS_DELAY_SEC="${NSYS_DELAY_SEC:-0}"
NSYS_DURATION_SEC="${NSYS_DURATION_SEC:-0}" # 0 means no duration limit
NSYS_WAIT_MODE="${NSYS_WAIT_MODE:-all}"     # all | primary | none

OUT_DIR="${NSYS_OUTPUT_ROOT}/pd"
mkdir -p "${OUT_DIR}"
OUTPUT_PREFIX="${OUT_DIR}/${NSYS_BASENAME}"

NSYS_CMD=(
  nsys profile
  --trace-fork-before-exec=true
  --cuda-graph-trace=node
  --trace="${NSYS_TRACE}"
  --force-overwrite="${NSYS_FORCE_OVERWRITE}"
  --output="${OUTPUT_PREFIX}"
)

if [[ "${NSYS_DELAY_SEC}" != "0" ]]; then
  NSYS_CMD+=(--delay "${NSYS_DELAY_SEC}")
fi
if [[ "${NSYS_DURATION_SEC}" != "0" ]]; then
  NSYS_CMD+=(--duration "${NSYS_DURATION_SEC}")
fi
if [[ -n "${NSYS_WAIT_MODE}" ]]; then
  NSYS_CMD+=(--wait "${NSYS_WAIT_MODE}")
fi

APP_CMD=(
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
  APP_CMD+=(--disaggregation-ib-device "${DISAGG_IB_DEVICE}")
fi
if [[ -n "${DECODE_BASE_GPU_ID}" ]]; then
  APP_CMD+=(--base-gpu-id "${DECODE_BASE_GPU_ID}")
fi
if [[ -n "${DECODE_MEM_FRACTION_STATIC}" ]]; then
  APP_CMD+=(--mem-fraction-static "${DECODE_MEM_FRACTION_STATIC}")
fi
if [[ -n "${DECODE_MAX_RUNNING_REQUESTS}" ]]; then
  APP_CMD+=(--max-running-requests "${DECODE_MAX_RUNNING_REQUESTS}")
fi
if [[ -n "${DECODE_EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARR=(${DECODE_EXTRA_ARGS})
  APP_CMD+=("${EXTRA_ARR[@]}")
fi

echo "Starting PD decode server with nsys..."
echo "Output prefix: ${OUTPUT_PREFIX}"
echo "Endpoint: http://${DECODE_HOST}:${DECODE_PORT}"
echo "Note: .nsys-rep is finalized when this server process exits (or duration is reached)."

if [[ -n "${DECODE_CUDA_DEVICES}" ]]; then
  CUDA_VISIBLE_DEVICES="${DECODE_CUDA_DEVICES}" "${NSYS_CMD[@]}" "${APP_CMD[@]}"
else
  "${NSYS_CMD[@]}" "${APP_CMD[@]}"
fi

echo
echo "Generated nsys files (decode):"
ls -1 "${OUTPUT_PREFIX}"* 2>/dev/null || echo "No files found for prefix: ${OUTPUT_PREFIX}"
