# Efficient Execution of Agentic Traces Using vLLM

**Research Project — Spring 2026, Neil Teje**

This repository contains a **live HyperAgent and vLLM-Continuum** path. AutoGen agents call your local Continuum server, each SWE-bench instance is one Continuum `job_id`, and per-request metrics are written to JSON. This section covers the HyperAgent Continuum support (`HyperAgent/src/hyperagent/continuum.py`, `pilot.py`, `run_swe_bench.py`). It does not cover `continuum_slo_framework/` or `hyperagent-replay/`.

---
Make sure you are in the repo root
```bash
pip install -e vllm-continuum
pip install -e HyperAgent
```
You also need
- A GPU machine (or RunPod pod) with enough VRAM for your model
- **Docker** for SWE-bench (`run_swe_bench.py` runs issue containers)
- The model weights pulled on the server host (via Hugging Face, ensure you authenticate HF_TOKEN)
---
### terminal 1
```bash
vllm serve Qwen/Qwen2.5-Coder-14B-Instruct \
  --scheduling-policy continuum \
  --host 127.0.0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768
```
Wait until the server responds:
```bash
curl -s http://127.0.0.1:8000/v1/models
```
Use `--tensor-parallel-size N` if the model does not fit on one GPU.
### terminal 2 (this one is for hyperagent)
```bash
cd HyperAgent
export HYPERAGENT_CONTINUUM_ENABLED=1
export HYPERAGENT_CONTINUUM_BASE_URL=http://127.0.0.1:8000/v1
export HYPERAGENT_CONTINUUM_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct
export HYPERAGENT_CONTINUUM_API_KEY=EMPTY
python scripts/run_swe_bench.py \
  --backend continuum \
  --continuum_base_url "$HYPERAGENT_CONTINUUM_BASE_URL" \
  --continuum_model "$HYPERAGENT_CONTINUUM_MODEL" \
  --instance_ids astropy__astropy-14209 \
  --split verified \
  --output_folder outputs/continuum \
  --continuum_metrics_folder ../results/hyperagent_continuum_metrics
```

## Programmatic use (for custom scripts)

```python
from hyperagent import HyperAgent
from hyperagent.continuum import build_continuum_llm_configs

import os
os.environ["HYPERAGENT_CONTINUUM_ENABLED"] = "1"

config = build_continuum_llm_configs(
    model="Qwen/Qwen2.5-Coder-14B-Instruct",
    base_url="http://127.0.0.1:8000/v1",
)

pilot = HyperAgent(
    repo_path="...",
    commit="...",
    llm_configs=config,
    continuum_job_id="my-job-1",
    continuum_metrics_path="results/hyperagent_continuum_metrics/my-job-1.metrics.json",
)
```