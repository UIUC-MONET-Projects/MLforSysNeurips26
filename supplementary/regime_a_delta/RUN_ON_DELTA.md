# Phase 2: Regime A (serial, single-job) — HyperAgent × vLLM / vLLM-Continuum

**Goal (Regime A)**. One trace at a time, serial turns. We're optimizing the
*per-job* path, so we measure only Continuum's **KV-pinning** benefit (the
scheduler has nothing to reorder inside a serial trace). Cleanest
apples-to-apples against the existing baseline and reuse replays in
`hyperagent-replay/replays-two/`.

The 2×2 cell matrix we want to fill:

| cell | engine                | reuse              | driver                        |
| ---- | --------------------- | ------------------ | ----------------------------- |
| A    | stock vLLM            | none (baseline)    | `ha-trace-batch-replay`       |
| B    | stock vLLM            | sub-agent reuse    | `ha-trace-replay-reuse`       |
| C    | **vllm-continuum**    | none               | `ha-trace-batch-replay --engine-mode continuum` |
| D    | **vllm-continuum**    | sub-agent reuse    | `ha-trace-replay-reuse --engine-mode continuum` |

Cells A/B come straight from `replays-two/` (already produced). Cells C/D
are what we run on the GPU node.

Every request in cells C/D carries:
- `job_id = trace.instance_id` — the whole trace is one Continuum job.
- `this_func_call = <normalized tool name>` — e.g. `open_file._run(...)` →
  `open_file` (omitted for pure-LLM turns). Drives KV-pinning duration.
- `is_last_step = True` on the final turn that actually hits the server
  (reuse mode skips cache-hit turns entirely, so `is_last_step` flips on
  the last non-cache-hit turn).

Continuum fills in `last_func_call` from its own history.

---

## 0) SSH to Delta / RunPod and grab a GPU

Delta:
```bash
ssh <your-username>@login.delta.ncsa.illinois.edu
srun -A <DELTA_ACCOUNT> -p gpuA100x4-interactive --gpus=1 --cpus-per-task=16 \
     --mem=64g --time=01:00:00 --pty /bin/bash
```

RunPod: use any 1×A100/H100 pod. Commands below assume a clone of MONET at
`$HOME/MONET` with `conda` / `mamba` available.

---

## 1) Environment

```bash
module load gcc-native/13.2 cudatoolkit/25.3_12.8  # Delta only

cd $HOME/MONET  # or wherever you cloned

conda create -n mast-continuum python=3.11 -y
conda activate mast-continuum
python -m pip install -U pip uv

# driver
python -m pip install -e hyperagent-replay

# serving engine: either stock vLLM or vllm-continuum (run separately)
python -m pip install -e vllm-continuum    # Continuum server (cells C/D)
# UV_TORCH_BACKEND=cu128 uv pip install vllm   # stock vLLM (cells A/B)
```

The `vllm-continuum` editable install builds against its vendored
`setup.py` and provides both the server (`vllm serve ... --scheduling-policy
continuum`) and a regular OpenAI-compatible endpoint.

Our small patch in `vllm/v1/core/estimate_with_func.py` makes the server
**preserve client-provided `this_func_call`** (the built-in regex only
matches ```` ```bash ```` fences, which HyperAgent rarely emits).

---

## 2) Terminal A — start the server you want to test

### Cells A/B — stock vLLM (FCFS)

```bash
cd $HOME/MONET
conda activate mast-continuum
vllm serve Qwen/Qwen2.5-Coder-14B-Instruct \
  --host 127.0.0.1 --port 8000 \
  --gpu-memory-utilization 0.90 --max-model-len 32768
```

### Cells C/D — vllm-continuum (job-level FCFS + KV pinning)

```bash
cd $HOME/MONET
conda activate mast-continuum
vllm serve Qwen/Qwen2.5-Coder-14B-Instruct \
  --scheduling-policy continuum \
  --host 127.0.0.1 --port 8000 \
  --gpu-memory-utilization 0.90 --max-model-len 32768
```

Leave the server running.

---

## 3) Terminal B — fill the 4 cells

The helper below (committed in this folder) runs the full 2×2 for a fixed
list of traces, resetting the server prefix cache between traces for fair
comparison:

```bash
bash monet_research/phase2_mast_continuum/run_regime_a.sh \
  --input-dir hyperagent-replay/extracted \
  --output-root results/regime_a \
  --model Qwen/Qwen2.5-Coder-14B-Instruct \
  --limit 10
```

What it does, per cell:

- **Cell A (stock × baseline)**: `ha-trace-batch-replay --engine-mode stock
  --reset-prefix-cache-between-traces`. Output: `results/regime_a/A_stock_baseline/`.
- **Cell B (stock × reuse)**: one `ha-trace-replay-reuse --engine-mode stock`
  per trace, with a `/reset_prefix_cache` POST between traces.
- **Cell C (continuum × baseline)**: same as A with
  `--engine-mode continuum`. Requires the Continuum server. Each request
  carries `job_id`, `this_func_call`, `is_last_step`.
- **Cell D (continuum × reuse)**: same as B with `--engine-mode continuum`.
  `this_func_call` is only sent on turns that actually hit the server
  (cache hits skip the request entirely).

You can run A/B in one pass against the stock server, stop it, start the
Continuum server, then run C/D. The helper takes `--cells A,C` to do just
the subset you want.

### Manual invocation (one cell at a time)

```bash
# Cell A — stock, baseline, serial (Regime A)
ha-trace-batch-replay hyperagent-replay/extracted \
  --pattern "*.json" \
  --output-dir results/regime_a/A_stock_baseline \
  --model Qwen/Qwen2.5-Coder-14B-Instruct \
  --base-url http://127.0.0.1:8000/v1 \
  --max-model-len 32768 --max-completion-tokens 256 \
  --engine-mode stock \
  --reset-prefix-cache-between-traces \
  --limit 10

# Cell C — vllm-continuum, baseline, serial (Regime A)
ha-trace-batch-replay hyperagent-replay/extracted \
  --pattern "*.json" \
  --output-dir results/regime_a/C_continuum_baseline \
  --model Qwen/Qwen2.5-Coder-14B-Instruct \
  --base-url http://127.0.0.1:8000/v1 \
  --max-model-len 32768 --max-completion-tokens 256 \
  --engine-mode continuum \
  --reset-prefix-cache-between-traces \
  --limit 10

# Cell D — vllm-continuum + sub-agent reuse (one trace at a time)
for trace in hyperagent-replay/extracted/*.extracted.json; do
  ha-trace-replay-reuse "$trace" \
    --model Qwen/Qwen2.5-Coder-14B-Instruct \
    --base-url http://127.0.0.1:8000/v1 \
    --max-model-len 32768 --max-completion-tokens 256 \
    --engine-mode continuum \
    --output "results/regime_a/D_continuum_reuse/$(basename "${trace%.extracted.json}").reuse.replay.json"
done
```

---

## 4) Numbers to collect per cell

Every replay JSON now includes (per turn and aggregated in `timing`):

- `prompt_tokens` — full prefill length (what the model actually saw).
- `cached_prompt_tokens` — server-reported KV hits
  (`usage.prompt_tokens_details.cached_tokens`).
- `new_prefill_tokens = prompt_tokens - cached_prompt_tokens` — the
  **real** per-turn compute.
- `prefill_reuse_ratio` — total cached / total prompt. This is the
  cleanest single-number KPI for "did KV reuse actually help?".

For JCT and latency we keep the existing fields: `wall_solve_time_s`,
`lm_only_solve_time_s`, `avg/p50/p95/p99_request_latency_s`.

Scheduler-side JCT (Continuum-style) is produced side-by-side:

```bash
python vllm-continuum/continuum_exp/analyze.py \
  --input-dir results/regime_a/C_continuum_baseline \
  --output-dir results/regime_a/C_continuum_baseline/analysis
```

---

## 5a) Cross-cell comparator (work-avoided ratio + stage p95)

Once at least two cell directories are populated, run the comparator:

```bash
ha-trace-compare-regime-a \
  --cell A=results/regime_a/A_stock_baseline \
  --cell B=results/regime_a/B_stock_reuse \
  --cell C=results/regime_a/C_continuum_baseline \
  --cell D=results/regime_a/D_continuum_reuse \
  --baseline-cell A \
  --output-dir results/regime_a/compare
```

Outputs in `results/regime_a/compare/`:

- `per_trace.csv` — one row per (cell, trace): wall JCT, LM JCT = GPU-s,
  p50/p95/p99 measured latency (skipping cache-hit turns so they don't
  bias the tails to zero), prompt/cached/new-prefill/completion tokens,
  prefill reuse ratio, context retries, and
  **work_avoided_prefill/gpu_seconds/wall_vs_baseline** columns.
- `aggregate.csv` — per-cell means + **geomean speedup vs baseline**
  (`geomean_wall_speedup_vs_baseline`, `…gpu_seconds…`, `…prefill…`),
  computed only over traces present in every cell.
- `stage_p95.csv` — per (cell × agent × tool_signature) measured p50/p95/p99
  of `request_latency_s`. This tells you where the speedup lands
  (e.g. does Continuum pin pay off on `Navigator × open_file` but not
  `Planner × LLM_ONLY`?).

### Pulling Continuum scheduler events

The Continuum server writes its own `scheduler_timestamps` into
`$RUN_OUTPUT_DIR` (defaults to `./continuum_exp`). Start the server with
`RUN_OUTPUT_DIR=results/regime_a/C_continuum_baseline/server_events` so
the file ends up next to the replays, then:

```bash
ha-trace-compare-regime-a \
  --cell A=results/regime_a/A_stock_baseline \
  --cell C=results/regime_a/C_continuum_baseline \
  --baseline-cell A \
  --output-dir results/regime_a/compare \
  --continuum-scheduler-file results/regime_a/C_continuum_baseline/server_events/scheduler_timestamps
```

Adds `continuum_scheduler_events.csv` with per-`job_id`:
`num_pinned`, `total_pinned_duration_s`, `avg_pinned_duration_s`,
`num_evicted`, `num_waiting_to_running`, `queue_wait_p50_s`, `queue_wait_p95_s`.
That is the "did KV pinning actually fire?" diagnostic.

---

## 5) Print the meeting numbers (JCT + new-prefill)

```bash
python3 - <<'PY'
import glob, json, os, sys

ROOTS = {
  "A_stock_baseline":   "results/regime_a/A_stock_baseline",
  "B_stock_reuse":      "results/regime_a/B_stock_reuse",
  "C_continuum_baseline": "results/regime_a/C_continuum_baseline",
  "D_continuum_reuse":  "results/regime_a/D_continuum_reuse",
}

def safe(x, d=2):
    return "N/A" if x is None else f"{x:.{d}f}"

print(f"{'cell':<20} {'trace':<45} {'wall_s':>8} {'lm_s':>7} {'turns':>5} {'prompt':>9} {'cached':>9} {'new':>9} {'reuse%':>7}")
for cell, root in ROOTS.items():
    paths = sorted(glob.glob(os.path.join(root, "*.replay.json")))
    for p in paths:
        d = json.load(open(p))
        t = d.get("timing", {})
        wall = t.get("wall_solve_time_s")
        lm = t.get("lm_only_solve_time_s")
        n = t.get("num_replayed_turns", 0)
        pt = t.get("total_prompt_tokens", 0)
        ct = t.get("total_cached_prompt_tokens", 0)
        nt = t.get("total_new_prefill_tokens", pt)
        r = t.get("prefill_reuse_ratio", 0.0) * 100.0
        print(f"{cell:<20} {os.path.basename(p):<45} {safe(wall,1):>8} {safe(lm,1):>7} {n:>5} {pt:>9} {ct:>9} {nt:>9} {r:>6.1f}%")
PY
```

---

## 6) Smoke check (before running the matrix)

Against a running Continuum server, this confirms the client is sending
job metadata and the server sees it:

```bash
python3 - <<'PY'
import json, os, urllib.request
payload = {
  "model": os.environ.get("MODEL", "Qwen/Qwen2.5-Coder-14B-Instruct"),
  "messages": [{"role":"user","content":"say hello"}],
  "max_completion_tokens": 8,
  "job_id": "smoke-test-1",
  "this_func_call": "open_file",
  "is_last_step": False
}
req = urllib.request.Request(
  "http://127.0.0.1:8000/v1/chat/completions",
  data=json.dumps(payload).encode(),
  headers={"Content-Type":"application/json","Authorization":"Bearer EMPTY"})
print(urllib.request.urlopen(req, timeout=60).read().decode())
PY
```

The Continuum server log should print a line like
`Request job id arriving: smoke-test-1, ...`.

---

## 7) Notes / pitfalls

- **Stock vLLM ignores the extra fields**. That's by design — Cells A/B can
  use the same CLI with `--engine-mode stock` (or omit the flag) and the
  request payload stays vanilla.
- **Prefix cache between traces**. `--reset-prefix-cache-between-traces`
  ensures each trace starts cold. Omit it if you *want* cross-trace
  warmup (not Regime A).
- **Reuse + Continuum (Cell D)**. We skip `this_func_call` /
  `is_last_step` on cache-hit turns (no request is sent); `is_last_step`
  flips to True on the final *executed* turn so the Continuum scheduler
  releases the pin at the end of the job.
- **Continuum's `last_func_call` assertion**. We never send it from the
  client — the Continuum server asserts it's None on the first turn of a
  new `job_id` and fills it from history afterwards.
