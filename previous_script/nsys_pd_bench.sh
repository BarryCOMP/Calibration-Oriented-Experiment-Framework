#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/nsys_common.sh"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MODEL="${MODEL:-LLM-Research/Meta-Llama-3.1-8B-Instruct}"
TOKENIZER="${TOKENIZER:-${MODEL}}"

DATASET_NAME="${DATASET_NAME:-random}" # random | sharegpt | generated-shared-prefix
DATASET_PATH="${DATASET_PATH:-}"
NUM_PROMPTS="${NUM_PROMPTS:-100}"
SHAREGPT_OUTPUT_LEN="${SHAREGPT_OUTPUT_LEN:-512}"
RANDOM_INPUT_LEN="${RANDOM_INPUT_LEN:-256}"
RANDOM_OUTPUT_LEN="${RANDOM_OUTPUT_LEN:-128}"
RANDOM_RANGE_RATIO="${RANDOM_RANGE_RATIO:-0.0}"
MAX_CONCURRENCY="${MAX_CONCURRENCY:-}"
REQUEST_RATE="${REQUEST_RATE:-}"
BENCH_EXTRA_ARGS="${BENCH_EXTRA_ARGS:-}"

CMD=(
  python -m sglang.bench_serving
  --backend sglang
  --base-url "${BASE_URL}"
  --model "${MODEL}"
  --tokenizer "${TOKENIZER}"
  --dataset-name "${DATASET_NAME}"
  --num-prompts "${NUM_PROMPTS}"
)

if [[ "${DATASET_NAME}" == "random" ]]; then
  CMD+=(
    --random-input-len "${RANDOM_INPUT_LEN}"
    --random-output-len "${RANDOM_OUTPUT_LEN}"
    --random-range-ratio "${RANDOM_RANGE_RATIO}"
  )
elif [[ "${DATASET_NAME}" == "sharegpt" ]]; then
  CMD+=(--sharegpt-output-len "${SHAREGPT_OUTPUT_LEN}")
fi

if [[ -n "${DATASET_PATH}" ]]; then
  CMD+=(--dataset-path "${DATASET_PATH}")
fi
if [[ -n "${MAX_CONCURRENCY}" ]]; then
  CMD+=(--max-concurrency "${MAX_CONCURRENCY}")
fi
if [[ -n "${REQUEST_RATE}" ]]; then
  CMD+=(--request-rate "${REQUEST_RATE}")
fi
if [[ -n "${BENCH_EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARR=(${BENCH_EXTRA_ARGS})
  CMD+=("${EXTRA_ARR[@]}")
fi

echo "Running PD traffic benchmark (to trigger server-side nsys capture)..."
echo "Base URL: ${BASE_URL}"
echo "Model/tokenizer: ${MODEL}"
echo "Note: nsys trace files are produced by nsys_pd_p_server.sh and nsys_pd_d_server.sh."
echo "      They are usually finalized after those server processes exit."

"${CMD[@]}"

echo
echo "Current nsys files under ${NSYS_OUTPUT_ROOT}/pd:"
ls -1 "${NSYS_OUTPUT_ROOT}/pd" 2>/dev/null || echo "(pd output dir not found yet)"
