# Continuum SLO Framework

This folder is a runnable research scaffold for the next MONET direction:

1. Keep Continuum as the KV-cache-aware backend.
2. Add an SLO-aware queue/admission layer above it.
3. Evaluate multi-job agentic workloads under arrival-rate sweeps.

The goal is to answer Ragini's questions directly:

- Can agentic traces on Continuum be parallelized?
- Can we add SLOs and queues on top of Continuum?
- Can we plot job completion time, token usage, throughput, goodput, and SLO attainment?
- Can we produce resource-group size/queue-length vs arrival-rate curves?

## What Is Implemented

### 1. `proxy.py`

An OpenAI-compatible `/v1/chat/completions` proxy that sits between HyperAgent and Continuum.

```text
HyperAgent -> SLO Queue Proxy -> Continuum / vLLM server
```

It supports four queue policies:

- `fcfs`: first-come-first-served.
- `edf`: earliest-deadline-first.
- `cache_aware_edf`: earliest-deadline-first with a cache-reuse bonus.
- `slack_cache`: prioritize low slack, then cache-reuse likelihood, then aging.

It logs every request to JSONL with:

- arrival time
- queue wait
- service time
- total latency
- policy
- job id
- resource group id
- SLO deadline/budget
- prompt/completion/cached token usage if returned by the backend

### 2. `simulate_load.py`

A discrete-event simulator using your existing HyperAgent trace metrics from:

- `results/data/instance_summary.csv`
- `results/data/full_trace_per_turn.csv`

It sweeps arrival rate and policies, then writes:

- `outputs/slo_sweep.csv`: aggregate metrics per arrival rate/policy/backend.
- `outputs/job_level.csv`: per-job simulated arrivals, waits, JCT, SLO met/missed.

This gives immediate plots without needing a full cluster run.

### 3. `plot_slo.py`

Generates the scheduling plots the mentor asked for:

- SLO attainment vs arrival rate
- throughput and goodput vs arrival rate
- p95 JCT vs arrival rate
- mean queue wait vs arrival rate
- queue length in jobs vs arrival rate
- resource-group queue length vs arrival rate
- resource-group size vs arrival rate
- token usage vs arrival rate

## Quick Start: Offline Simulation

From repo root:

```bash
python3.11 continuum_slo_framework/simulate_load.py \
  --arrival-rates 0.002,0.004,0.006,0.008,0.010,0.012 \
  --policies fcfs,edf,cache_aware_edf,slack_cache \
  --backends stock_vllm,continuum \
  --jobs 300 \
  --workers 2 \
  --seed 7

python3.11 continuum_slo_framework/plot_slo.py
```

Outputs go to:

```text
continuum_slo_framework/outputs/
```

## Quick Start: Live Proxy

Terminal 1: start Continuum/vLLM.

```bash
cd vllm-continuum
vllm serve "$MODEL" --host 127.0.0.1 --port 8000
```

Terminal 2: start the SLO queue proxy.

```bash
pip install -r continuum_slo_framework/requirements.txt

python3.11 continuum_slo_framework/proxy.py \
  --upstream http://127.0.0.1:8000/v1 \
  --host 127.0.0.1 \
  --port 8010 \
  --policy cache_aware_edf \
  --workers 2 \
  --metrics-jsonl continuum_slo_framework/outputs/live_proxy_metrics.jsonl
```

Terminal 3: point HyperAgent to the proxy instead of Continuum directly.

```bash
export HYPERAGENT_CONTINUUM_BASE_URL="http://127.0.0.1:8010/v1"
```

## Recommended Experiment Arms

Run the same workload under:

1. stock vLLM FCFS
2. Continuum
3. Continuum + SLO queue proxy (`edf`)
4. Continuum + SLO queue proxy (`cache_aware_edf`)
5. Continuum + SLO queue proxy (`slack_cache`)

## Main Metrics To Report

For the paper/discussion, prioritize:

- SLO attainment: fraction of jobs with `jct <= slo_budget`.
- Goodput: jobs per second that meet SLO.
- JCT p50/p95/p99.
- Queue wait p50/p95.
- Prompt/completion/cached token usage.
- Cache hit rate / cached token ratio.
- Resource-group queue length vs arrival rate.
- Resource-group size vs arrival rate.

## Important Interpretation

Intra-agent DAG parallelism is likely limited because HyperAgent turns are mostly sequential.
The more realistic extension is workload-level parallelism:

- run many agent jobs concurrently;
- add an SLO queue above Continuum;
- let Continuum handle KV-cache pinning inside the backend;
- let the queue layer decide which job/turn gets admitted next.

This gives a defensible "Continuum++" research direction without requiring major changes to HyperAgent's reasoning loop.
