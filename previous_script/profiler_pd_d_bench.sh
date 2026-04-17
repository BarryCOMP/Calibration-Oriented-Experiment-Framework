#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pd_profile_common.sh"

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

PROFILE_DECODE_URLS="${PROFILE_DECODE_URLS:-http://127.0.0.1:30001}"
PROFILE_ACTIVITIES="${PROFILE_ACTIVITIES:-GPU}"
PROFILE_START_STEP="${PROFILE_START_STEP:-}"
PROFILE_STEPS="${PROFILE_STEPS:-}"
BENCH_EXTRA_ARGS="${BENCH_EXTRA_ARGS:-}"

read -r -a DECODE_URL_ARR <<< "${PROFILE_DECODE_URLS}"
read -r -a PROFILE_ACTIVITY_ARR <<< "${PROFILE_ACTIVITIES}"

mapfile -t BEFORE_TRACES < <(find "${SGLANG_TORCH_PROFILER_DIR}" -type f -name "*.trace.json.gz" 2>/dev/null | sort)

CMD=(
  python -m sglang.bench_serving
  --backend sglang
  --base-url "${BASE_URL}"
  --model "${MODEL}"
  --tokenizer "${TOKENIZER}"
  --dataset-name "${DATASET_NAME}"
  --num-prompts "${NUM_PROMPTS}"
  --profile
  --profile-activities "${PROFILE_ACTIVITY_ARR[@]}"
  --pd-separated
  --profile-decode-url "${DECODE_URL_ARR[@]}"
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

if [[ -n "${PROFILE_START_STEP}" ]]; then
  CMD+=(--profile-start-step "${PROFILE_START_STEP}")
fi

if [[ -n "${PROFILE_STEPS}" ]]; then
  CMD+=(--profile-steps "${PROFILE_STEPS}")
fi

if [[ -n "${BENCH_EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARR=(${BENCH_EXTRA_ARGS})
  CMD+=("${EXTRA_ARR[@]}")
fi

echo "Profiling PD decode worker(s) with torch profiler..."
echo "Traffic endpoint: ${BASE_URL}"
echo "Profile target (decode): ${PROFILE_DECODE_URLS}"
echo "Profiler root: ${SGLANG_TORCH_PROFILER_DIR}"

"${CMD[@]}"

mapfile -t AFTER_TRACES < <(find "${SGLANG_TORCH_PROFILER_DIR}" -type f -name "*.trace.json.gz" 2>/dev/null | sort)

echo
echo "New trace files:"
NEW_COUNT=0
for f in "${AFTER_TRACES[@]}"; do
  is_new=1
  for old in "${BEFORE_TRACES[@]}"; do
    if [[ "${f}" == "${old}" ]]; then
      is_new=0
      break
    fi
  done
  if [[ ${is_new} -eq 1 ]]; then
    echo "  ${f}"
    NEW_COUNT=$((NEW_COUNT + 1))
  fi
done

if [[ ${NEW_COUNT} -eq 0 ]]; then
  echo "  (No new .trace.json.gz detected; check server/client profiler settings.)"
fi
