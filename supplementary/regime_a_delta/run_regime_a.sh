#!/usr/bin/env bash
# Run Regime A (serial, single-job) cells of the 2x2 matrix for HyperAgent
# traces against whichever vLLM server is currently listening on --base-url.
#
# Cells:
#   A: stock vLLM, no reuse  (ha-trace-batch-replay --engine-mode stock)
#   B: stock vLLM, sub-agent reuse  (ha-trace-replay-reuse --engine-mode stock)
#   C: vllm-continuum, no reuse     (ha-trace-batch-replay --engine-mode continuum)
#   D: vllm-continuum, reuse        (ha-trace-replay-reuse --engine-mode continuum)
#
# Cells A/B target a stock vLLM server.
# Cells C/D target a vllm-continuum server started with
#   `--scheduling-policy continuum`.
#
# The script does NOT start/stop servers. You control which server is up.
#
# Usage:
#   bash run_regime_a.sh --input-dir hyperagent-replay/extracted \
#                        --output-root results/regime_a \
#                        --model Qwen/Qwen2.5-Coder-14B-Instruct \
#                        [--base-url http://127.0.0.1:8000/v1] \
#                        [--cells A,B,C,D] \
#                        [--limit 10] [--offset 0] \
#                        [--max-model-len 32768] \
#                        [--max-completion-tokens 256] \
#                        [--pattern '*.json']

set -euo pipefail

INPUT_DIR=""
OUTPUT_ROOT=""
MODEL=""
BASE_URL="http://127.0.0.1:8000/v1"
CELLS="A,B,C,D"
LIMIT=""
OFFSET="0"
MAX_MODEL_LEN="32768"
MAX_COMPLETION_TOKENS="256"
PATTERN="*.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir) INPUT_DIR="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --cells) CELLS="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --offset) OFFSET="$2"; shift 2 ;;
    --max-model-len) MAX_MODEL_LEN="$2"; shift 2 ;;
    --max-completion-tokens) MAX_COMPLETION_TOKENS="$2"; shift 2 ;;
    --pattern) PATTERN="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,28p' "$0"; exit 0 ;;
    *)
      echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$INPUT_DIR" || -z "$OUTPUT_ROOT" || -z "$MODEL" ]]; then
  echo "--input-dir, --output-root, and --model are required." >&2
  exit 2
fi

mkdir -p "$OUTPUT_ROOT"

have_cell() {
  [[ ",${CELLS}," == *",$1,"* ]]
}

limit_args=()
if [[ -n "$LIMIT" ]]; then
  limit_args=(--limit "$LIMIT")
fi

common_batch_args=(
  --pattern "$PATTERN"
  --model "$MODEL"
  --base-url "$BASE_URL"
  --max-model-len "$MAX_MODEL_LEN"
  --max-completion-tokens "$MAX_COMPLETION_TOKENS"
  --reset-prefix-cache-between-traces
  --offset "$OFFSET"
  "${limit_args[@]}"
)

reset_cache() {
  local url="${BASE_URL%/v1}/reset_prefix_cache"
  curl -sS -X POST "$url" -o /dev/null -w 'reset_prefix_cache => %{http_code}\n' || true
}

run_reuse_over_dir() {
  local out_dir="$1"
  local engine_mode="$2"
  mkdir -p "$out_dir"
  # Match batch-replay's discovery order (lexicographic absolute path).
  local i=0
  local limit_int
  limit_int="${LIMIT:-}"
  # Iterate the same traces that batch_replay would pick up.
  local paths=()
  while IFS= read -r -d '' p; do
    paths+=("$p")
  done < <(find "$INPUT_DIR" -type f -name "$PATTERN" \
            ! -name '*.replay.json' ! -name '*.eval.json' ! -name '*.summary.json' \
            -print0 | sort -z)
  local start=$OFFSET
  local end
  if [[ -n "$limit_int" ]]; then
    end=$((start + limit_int))
  else
    end=${#paths[@]}
  fi
  for ((k=start; k<end && k<${#paths[@]}; k++)); do
    local trace="${paths[$k]}"
    local base
    base="$(basename "$trace")"
    base="${base%.extracted.json}"
    base="${base%.json}"
    local out="$out_dir/${base}.reuse.replay.json"
    echo "[regime_a] [reuse/$engine_mode] ($((k+1))/${end}) $base"
    reset_cache
    ha-trace-replay-reuse "$trace" \
      --model "$MODEL" \
      --base-url "$BASE_URL" \
      --max-model-len "$MAX_MODEL_LEN" \
      --max-completion-tokens "$MAX_COMPLETION_TOKENS" \
      --engine-mode "$engine_mode" \
      --output "$out"
  done
}

if have_cell A; then
  echo "=== Cell A: stock vLLM, baseline ==="
  ha-trace-batch-replay "$INPUT_DIR" \
    --output-dir "$OUTPUT_ROOT/A_stock_baseline" \
    --engine-mode stock \
    "${common_batch_args[@]}"
fi

if have_cell B; then
  echo "=== Cell B: stock vLLM + sub-agent reuse ==="
  run_reuse_over_dir "$OUTPUT_ROOT/B_stock_reuse" stock
fi

if have_cell C; then
  echo "=== Cell C: vllm-continuum, baseline ==="
  ha-trace-batch-replay "$INPUT_DIR" \
    --output-dir "$OUTPUT_ROOT/C_continuum_baseline" \
    --engine-mode continuum \
    "${common_batch_args[@]}"
fi

if have_cell D; then
  echo "=== Cell D: vllm-continuum + sub-agent reuse ==="
  run_reuse_over_dir "$OUTPUT_ROOT/D_continuum_reuse" continuum
fi

echo "Done. Outputs under $OUTPUT_ROOT"
