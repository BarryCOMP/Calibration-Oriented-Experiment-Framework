#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/nsys_common.sh"

ROUTER_HOST="${ROUTER_HOST:-0.0.0.0}"
ROUTER_PORT="${ROUTER_PORT:-8000}"
PREFILL_URLS="${PREFILL_URLS:-http://127.0.0.1:30000}"
DECODE_URLS="${DECODE_URLS:-http://127.0.0.1:30001}"
ROUTER_LOG_LEVEL="${ROUTER_LOG_LEVEL:-info}"
ROUTER_EXTRA_ARGS="${ROUTER_EXTRA_ARGS:-}"

read -r -a PREFILL_ARR <<< "${PREFILL_URLS}"
read -r -a DECODE_ARR <<< "${DECODE_URLS}"

CMD=(
  python -m sglang_router.launch_router
  --pd-disaggregation
  --prefill "${PREFILL_ARR[@]}"
  --decode "${DECODE_ARR[@]}"
  --host "${ROUTER_HOST}"
  --port "${ROUTER_PORT}"
  --log-level "${ROUTER_LOG_LEVEL}"
)

if [[ -n "${ROUTER_EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARR=(${ROUTER_EXTRA_ARGS})
  CMD+=("${EXTRA_ARR[@]}")
fi

echo "Starting PD router (no nsys needed)..."
echo "Router endpoint: http://${ROUTER_HOST}:${ROUTER_PORT}"
echo "Prefill backends: ${PREFILL_URLS}"
echo "Decode backends: ${DECODE_URLS}"

"${CMD[@]}"
