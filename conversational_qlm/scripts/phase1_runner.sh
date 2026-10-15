#!/bin/bash
# Phase 1: ShareGPT Baseline Experiments Runner
# This script runs all 12 baseline experiments comparing vLLM and QLM

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# packaging: QLMDIR/RESULTSDIR may be overridden from the environment
QLMDIR="${QLMDIR:-${REPO_ROOT}/QLM}"
RESULTSDIR="${RESULTSDIR:-${REPO_ROOT}/results/phase1}"
VLLM_PORT=8000
VLLM_ADDRESS="${VLLM_ADDRESS:-localhost}"
MODEL="unsloth/Llama-3.2-1B-Instruct"
DURATION=60  # seconds per experiment
MAX_SAMPLES=1000

# Create results directory
mkdir -p "$RESULTSDIR"

# Export QLM project directory
export QLMPROJDIR="$QLMDIR"

cd "$QLMDIR"

echo "=========================================="
echo "Phase 1: ShareGPT Baseline Experiments"
echo "=========================================="
echo "Results will be saved to: $RESULTSDIR"
echo ""

# Function to run vLLM experiment
run_vllm_experiment() {
    local exp_id=$1
    local arrival_rate=$2
    local burst_size=$3
    local burst_interval=$4
    local num_users=$5
    local prompt_length=$6
    local output_file=$7
    
    echo "Running $exp_id: vLLM (rate=$arrival_rate, burst=$burst_size, users=$num_users, prompts=$prompt_length)"
    
    if [ "$burst_size" -gt 1 ]; then
        python benchmarks/workload_driver.py \
            --dataset sharegpt \
            --duration $DURATION \
            --max-samples $MAX_SAMPLES \
            --burst-size $burst_size \
            --burst-interval $burst_interval \
            --num-users $num_users \
            --model $MODEL \
            --address "$VLLM_ADDRESS" \
            --port $VLLM_PORT \
            --no-start-vllm \
            ${prompt_length:+--prompt-length $prompt_length} \
            --output "$RESULTSDIR/$output_file"
    else
        python benchmarks/workload_driver.py \
            --dataset sharegpt \
            --duration $DURATION \
            --max-samples $MAX_SAMPLES \
            --arrival-rate $arrival_rate \
            --num-users $num_users \
            --model $MODEL \
            --address "$VLLM_ADDRESS" \
            --port $VLLM_PORT \
            --no-start-vllm \
            ${prompt_length:+--prompt-length $prompt_length} \
            --output "$RESULTSDIR/$output_file"
    fi
    
    echo "✓ Completed $exp_id"
    echo ""
}

# Function to run QLM experiment
run_qlm_experiment() {
    local exp_id=$1
    local arrival_rate=$2
    local burst_size=$3
    local burst_interval=$4
    local num_users=$5
    local prompt_length=$6
    local output_file=$7
    
    echo "Running $exp_id: QLM (rate=$arrival_rate, burst=$burst_size, users=$num_users, prompts=$prompt_length)"
    
    # Note: QLM experiments use the same workload_driver.py
    # The difference is in the QLM queue configuration (SLO settings)
    
    if [ "$burst_size" -gt 1 ]; then
        python benchmarks/workload_driver.py \
            --dataset sharegpt \
            --duration $DURATION \
            --max-samples $MAX_SAMPLES \
            --burst-size $burst_size \
            --burst-interval $burst_interval \
            --num-users $num_users \
            --model $MODEL \
            --address "$VLLM_ADDRESS" \
            --port $VLLM_PORT \
            --no-start-vllm \
            ${prompt_length:+--prompt-length $prompt_length} \
            --output "$RESULTSDIR/$output_file"
    else
        python benchmarks/workload_driver.py \
            --dataset sharegpt \
            --duration $DURATION \
            --max-samples $MAX_SAMPLES \
            --arrival-rate $arrival_rate \
            --num-users $num_users \
            --model $MODEL \
            --address "$VLLM_ADDRESS" \
            --port $VLLM_PORT \
            --no-start-vllm \
            ${prompt_length:+--prompt-length $prompt_length} \
            --output "$RESULTSDIR/$output_file"
    fi
    
    echo "✓ Completed $exp_id"
    echo ""
}

echo "=========================================="
echo "IMPORTANT: Make sure vLLM server is running!"
echo "Start it with:"
echo "  vllm serve $MODEL --port $VLLM_PORT"
echo "=========================================="
echo ""
read -p "Press Enter when vLLM server is ready..."

# Experiment E1.1: vLLM baseline (mixed prompts, 2 rps)
run_vllm_experiment "E1.1" 2 1 2.0 1 "" "vllm_baseline_mixed.json"

# Experiment E1.2: QLM baseline (mixed prompts, 2 rps)
run_qlm_experiment "E1.2" 2 1 2.0 1 "" "qlm_baseline_mixed.json"

# Experiment E1.3: vLLM high rate (5 rps)
run_vllm_experiment "E1.3" 5 1 2.0 1 "" "vllm_high_rate.json"

# Experiment E1.4: QLM high rate (5 rps)
run_qlm_experiment "E1.4" 5 1 2.0 1 "" "qlm_high_rate.json"

# Experiment E1.5: vLLM bursty (5 requests every 2 seconds)
run_vllm_experiment "E1.5" 2 5 2.0 1 "" "vllm_bursty.json"

# Experiment E1.6: QLM bursty (5 requests every 2 seconds)
run_qlm_experiment "E1.6" 2 5 2.0 1 "" "qlm_bursty.json"

# Experiment E1.7: vLLM multi-user (8 concurrent users)
run_vllm_experiment "E1.7" 2 1 2.0 8 "" "vllm_multiuser.json"

# Experiment E1.8: QLM multi-user (8 concurrent users)
run_qlm_experiment "E1.8" 2 1 2.0 8 "" "qlm_multiuser.json"

# Experiment E1.9: vLLM short prompts
run_vllm_experiment "E1.9" 2 1 2.0 1 "short" "vllm_short_prompts.json"

# Experiment E1.10: QLM short prompts
run_qlm_experiment "E1.10" 2 1 2.0 1 "short" "qlm_short_prompts.json"

# Experiment E1.11: vLLM long prompts
run_vllm_experiment "E1.11" 2 1 2.0 1 "long" "vllm_long_prompts.json"

# Experiment E1.12: QLM long prompts
run_qlm_experiment "E1.12" 2 1 2.0 1 "long" "qlm_long_prompts.json"

echo "=========================================="
echo "✓ All Phase 1 experiments completed!"
echo "=========================================="
echo "Results saved to: $RESULTSDIR"
echo ""
echo "Next steps:"
echo "1. Analyze results with: jupyter notebook analysis/phase1_sharegpt.ipynb"
echo "2. Generate plots for report"
echo "3. Update Overleaf with methodology and results"
echo ""
