#!/bin/bash
# Setup Validator - Check if everything is ready for Phase 1 experiments

set +e  # Don't exit on error (we want to check everything)

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
QLMDIR="${QLMDIR:-${REPO_ROOT}/QLM}"  # packaging: env override allowed
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Phase 1 Setup Validator"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Check 1: QLM directory exists
echo -n "Checking QLM directory... "
if [ -d "$QLMDIR" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    echo "  Error: QLM directory not found at $QLMDIR"
    ERRORS=$((ERRORS + 1))
fi

# Check 2: QLM Python package installed
echo -n "Checking QLM installation... "
cd "$QLMDIR" 2>/dev/null
if python -c "import qlm" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    echo "  Error: QLM package not installed. Run: cd QLM && pip install -e ."
    ERRORS=$((ERRORS + 1))
fi

# Check 3: Required Python packages
echo -n "Checking required packages... "
MISSING_PACKAGES=""
for pkg in numpy pandas matplotlib seaborn datasets; do
    if ! python -c "import $pkg" 2>/dev/null; then
        MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
    fi
done

if [ -z "$MISSING_PACKAGES" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: Missing packages:$MISSING_PACKAGES"
    echo "  Install with: pip install$MISSING_PACKAGES"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 4: ShareGPT dataset
echo -n "Checking ShareGPT dataset... "
SHAREGPT_PATH="$QLMDIR/data/ShareGPT_V3_unfiltered_cleaned_split.json"
if [ -f "$SHAREGPT_PATH" ]; then
    SIZE=$(du -h "$SHAREGPT_PATH" | cut -f1)
    echo -e "${GREEN}✓${NC} ($SIZE)"
else
    echo -e "${RED}✗${NC}"
    echo "  Error: ShareGPT dataset not found at $SHAREGPT_PATH"
    echo "  Download with:"
    echo "    cd $QLMDIR/data"
    echo "    wget https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered/resolve/main/ShareGPT_V3_unfiltered_cleaned_split.json"
    ERRORS=$((ERRORS + 1))
fi

# Check 5: vLLM installation
echo -n "Checking vLLM installation... "
if python -c "import vllm" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    echo "  Error: vLLM not installed. Install with: pip install vllm"
    ERRORS=$((ERRORS + 1))
fi

# Check 6: vLLM server running
echo -n "Checking vLLM server (port 8000)... "
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: vLLM server not running on port 8000"
    echo "  Start with: vllm serve unsloth/Llama-3.2-1B-Instruct --port 8000"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 7: Results directory
echo -n "Checking results directory... "
RESULTSDIR="${RESULTSDIR:-${REPO_ROOT}/results/phase1}"  # packaging: env override allowed
if [ -d "$RESULTSDIR" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: Results directory doesn't exist. Creating..."
    mkdir -p "$RESULTSDIR"
    if [ -d "$RESULTSDIR" ]; then
        echo "  Created: $RESULTSDIR"
    else
        echo "  Error: Failed to create results directory"
        ERRORS=$((ERRORS + 1))
    fi
fi

# Check 8: Analysis directory
echo -n "Checking analysis directory... "
ANALYSISDIR="${REPO_ROOT}/analysis"
if [ -d "$ANALYSISDIR" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: Analysis directory doesn't exist. Creating..."
    mkdir -p "$ANALYSISDIR/plots"
    if [ -d "$ANALYSISDIR" ]; then
        echo "  Created: $ANALYSISDIR"
    else
        echo "  Error: Failed to create analysis directory"
        ERRORS=$((ERRORS + 1))
    fi
fi

# Check 9: Jupyter installation
echo -n "Checking Jupyter... "
if command -v jupyter >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: Jupyter not installed. Install with: pip install jupyter"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 10: GPU availability
echo -n "Checking GPU availability... "
if python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    GPU_COUNT=$(python -c "import torch; print(torch.cuda.device_count())")
    GPU_NAME=$(python -c "import torch; print(torch.cuda.get_device_name(0))")
    echo -e "${GREEN}✓${NC} ($GPU_COUNT GPU: $GPU_NAME)"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: No GPU detected. Experiments will be slow or may fail."
    echo "  Make sure you're running on a GPU-enabled machine (Delta cluster)."
    WARNINGS=$((WARNINGS + 1))
fi

# Check 11: QLMPROJDIR environment variable
echo -n "Checking QLMPROJDIR... "
if [ -n "$QLMPROJDIR" ]; then
    echo -e "${GREEN}✓${NC} ($QLMPROJDIR)"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: QLMPROJDIR not set. Set with: export QLMPROJDIR=$QLMDIR"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 12: Gurobi (optional)
echo -n "Checking Gurobi (optional)... "
if python -c "import gurobipy" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC}"
    echo "  Warning: Gurobi not installed (optional for QLM LP scheduler)"
    echo "  QLM will use heuristic scheduler instead."
    WARNINGS=$((WARNINGS + 1))
fi

# Summary
echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! You're ready to run experiments.${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Start vLLM server (if not running):"
    echo "   vllm serve unsloth/Llama-3.2-1B-Instruct --port 8000"
    echo ""
    echo "2. Run Phase 1 experiments:"
    echo "   cd $QLMDIR"
    echo "   ../scripts/phase1_runner.sh"
    echo ""
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Setup complete with $WARNINGS warning(s).${NC}"
    echo "You can proceed, but some features may not work."
    echo ""
else
    echo -e "${RED}✗ Setup incomplete: $ERRORS error(s), $WARNINGS warning(s).${NC}"
    echo "Please fix the errors above before running experiments."
    echo ""
    exit 1
fi

# Quick test option
echo "=========================================="
echo "Quick Test (Optional)"
echo "=========================================="
echo "Run a quick 10-second test to verify everything works?"
read -p "Press Enter to run test, or Ctrl+C to skip... "

echo ""
echo "Running quick test (10 seconds, 50 samples)..."
cd "$QLMDIR"
export QLMPROJDIR="$QLMDIR"

python benchmarks/workload_driver.py \
    --dataset sharegpt \
    --duration 10 \
    --max-samples 50 \
    --arrival-rate 2 \
    --no-start-vllm \
    --output /tmp/test_metrics.json

if [ $? -eq 0 ] && [ -f /tmp/test_metrics.json ]; then
    echo ""
    echo -e "${GREEN}✓ Quick test passed!${NC}"
    echo ""
    echo "Test results:"
    python -c "
import json
with open('/tmp/test_metrics.json') as f:
    data = json.load(f)
    print(f\"  Duration: {data.get('duration_sec', 0):.1f} seconds\")
    print(f\"  Requests: {data['summary']['num_requests_dispatched']}\")
    print(f\"  Mean delay: {data['summary']['scheduling_delay_ms_mean']:.2f} ms\")
    print(f\"  Mean queue: {data['summary']['queue_length_mean']:.2f}\")
"
    echo ""
    echo -e "${GREEN}Setup validated successfully! Ready for Phase 1.${NC}"
else
    echo ""
    echo -e "${RED}✗ Quick test failed.${NC}"
    echo "Check the error messages above and verify vLLM server is running."
    exit 1
fi
