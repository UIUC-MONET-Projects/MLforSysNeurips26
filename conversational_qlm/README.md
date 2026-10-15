# Conversational workloads: vLLM vs QLM on ShareGPT

Paper: Section 2.1 (setup), Section 3.1 (results), Table 1 (`tab:chat`), and Appendix A: Table 2 (`tab:full_results`),
Figures 4–6 (`fig:app_delay`, `fig:queue_regimes`, `fig:app_prompt`). The source is MONET `monet_research/`.
Every MONET commit touching it is by Neil Teje.

| Path | What | Used by the paper |
|---|---|---|
| `scripts/phase1_runner.sh` | Runs the 12 experiments (E1.1–E1.12) with the patched QLM's `benchmarks/workload_driver.py` | produced `results/phase1/` |
| `scripts/validate_setup.sh` | Environment checks and a 10 s smoke run | no |
| `results/phase1/*.json` | Raw metrics for the 12 runs: per-request scheduling delays, queue length every 0.25 s, backpressure, summary | yes (all tables and appendix figures) |
| `phase1_sharegpt.ipynb` | Analysis notebook (saved outputs included). Writes `plots/` | yes: Table 2 (`plots/summary_table.tex`), numbers in Table 1 |
| `plots/` | Notebook outputs: `summary_statistics.csv`, `summary_table.tex`, five PNGs | `summary_table.tex` is byte-identical to `MLSYS2/summary_table.tex` |
| `generate_phase1_pretty_plots.py` | Publication-style versions of the five plots (uses pretty-plots). Writes `plots_pretty/` | yes: Figures 4–6 |
| `plots_pretty/` | Script outputs (PNG and PDF) | `plot1` is byte-identical to the paper's Fig. 4; `plot2` and `plot4` are the paper's Figs. 5 and 6 before manual cropping |

`generate_phase1_pretty_plots.py` is not in MONET's current tree. It was added in MONET commit `0799a40`
(2026-04-18, as `analysis/generate_phase1_pretty_plots.py`), moved in `975cf9f`, and deleted in `04f8583`
(2026-05-21). It was recovered verbatim from `04f8583^` with two packaging edits; see `PROVENANCE.md`.
`plots_pretty/*.pdf` record Matplotlib 3.10.8 and creation time 2026-04-18 09:10:59 -05:00, consistent with that script.

## Regenerating the tables and figures from the included data

```bash
pip install -r conversational_qlm/requirements.txt
# Table 2 + summary_statistics.csv + notebook PNGs (overwrites conversational_qlm/plots/)
cd conversational_qlm && jupyter nbconvert --to notebook --execute --inplace phase1_sharegpt.ipynb && cd ..
# Figures 4-6 (overwrites conversational_qlm/plots_pretty/); needs <repo root>/pretty-plots, see patches/README.md
python conversational_qlm/generate_phase1_pretty_plots.py
```

* **Table 2** = `plots/summary_table.tex` (notebook cell 19, `DataFrame.to_latex`).
* **Table 1** values were typed into the paper. Delay and queue values come from `plots/summary_statistics.csv`.
  Throughput is `num_requests_dispatched / duration_sec`, as in the notebook's plot-3 cell. Recomputed from
  `results/phase1`: E1.3 276/60.084 = 4.594 and E1.4 286/60.095 = 4.759 req/s (paper: 4.6 / 4.8); E1.7 287/60.130 = 4.773
  and E1.8 290/60.117 = 4.824 req/s (paper: ~4.8). p99 151.16 / 47.43 ms (E1.1/E1.2), 110.35 / 50.21 ms (E1.11/E1.12).
  Mean queue 11.08 / 9.19 (E1.3/E1.4).
* **Fig. 4** = `plots_pretty/plot1_scheduling_delay_baseline.png` (same bytes as `MLSYS2/plot1_scheduling_delay_baseline.png`).
* **Fig. 5** = `plots_pretty/plot2_queue_length_over_time.png` with its panel titles removed by hand (2058×1456 → 2058×1389 px).
* **Fig. 6** = `plots_pretty/plot4_prompt_length_sensitivity.png` with its top 55 px (panel titles) cropped by hand (2038×703 → 2038×648 px).
  No code in MONET does the cropping.
* Exact styling needs pretty-plots at `15c2e83` and the "Times New Roman" font.

## Re-running the experiments (GPU)

The earlier write-up in MONET (`monet_research/agenticVLLM.tex`, a paper draft not shipped here) states that the runs used
`unsloth/Llama-3.2-1B-Instruct` on one NVIDIA L4 (RunPod). The runner hard-codes that model, 60 s per run and up to 1000 prompts.

```bash
# 1. patched QLM (see patches/README.md), ShareGPT file inside it
export QLMDIR=$PWD/third_party/QLM
mkdir -p "$QLMDIR/data" && wget -O "$QLMDIR/data/ShareGPT_V3_unfiltered_cleaned_split.json" \
  https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered/resolve/main/ShareGPT_V3_unfiltered_cleaned_split.json
# expected SHA-256 of the copy used in MONET: 35f0e213ce091ed9b9af2a1f0755e9d39f9ccec34ab281cd4ca60d70f6479ba4
pip install -e "$QLMDIR" && pip install -r "$QLMDIR/requirements.txt"
# 2. in another terminal: vllm serve unsloth/Llama-3.2-1B-Instruct --port 8000
# 3. write to a NEW directory so the shipped paper data is not overwritten
RESULTSDIR=$PWD/conversational_qlm/results/rerun bash conversational_qlm/scripts/phase1_runner.sh
```

Prompt selection is deterministic. `qlm/workload/datasets.py` walks ShareGPT in file order, skips conversations with fewer
than 2 turns or an empty first message, and keeps the first message (whatever its role) until it has 1,000 prompts. The
short/long buckets (≤200 / >1000 chars) are filtered from those 1,000.

## Caveats for auditors

1. **The vLLM and QLM conditions run the same command.** In `scripts/phase1_runner.sh`, `run_vllm_experiment` and
   `run_qlm_experiment` run the same `python benchmarks/workload_driver.py ...` command line. `workload_driver.py`
   always sends requests through QLM's `Queue`. Neither script sets `QLM_SCHEDULER_POLICY` (default `edf`) or `--slo`
   (default 1000 s for every request). With one model and one SLO there is a single QLM request group, so EDF
   reordering has nothing to reorder. The result JSONs carry no system identifier. Nothing in MONET records how the
   "vLLM" runs were configured differently from the "QLM" runs. The deleted MONET doc
   `04f8583^:monet_research/docs/QUICKSTART.md` also lists identical commands for E1.1 and E1.2.
2. **Scheduling delay is not the time since arrival.** `ExperimentMetrics.record_scheduling_delay` (in
   `patches/QLM.patch`) records `dispatch_time - request.insertion_time`. Upstream QLM's `Scheduler._update_all_slos`
   (`qlm/scheduler/scheduler.py`, line 45 after patching; not changed by the patch) sets
   `request.insertion_time = curr_time` for every queued request, and `Queue.run_queue` reaches it on every loop
   iteration (`reorder_vqs()` -> `check_violation()`). QLM's own `push()` docstring says the insertion time "can be
   updated during request lifetime". The recorded value is therefore the time since the start of the latest loop
   iteration, which is mostly the three blocking `/metrics` reads in `get_backpressure()`, not the time since `push()`.
   Evidence in the shipped data: in every run, each dispatched request's recorded `insertion_time` is later than the
   previous dispatch (286/286 in E1.7, despite a queue of several hundred requests), and at 16 req/s the recorded mean
   delay is 0.033 s while the mean queue (334 requests at about 4.8 dispatches/s) implies about 70 s by Little's law.
   The value excludes model execution.
3. **p99 definition.** `qlm/workload/metrics.py` (in `patches/QLM.patch`) computes p99 as `sorted(delays)[int(0.99*n)]` and
   p50 as `sorted(delays)[n//2]`. With n = 120 requests, p99 is the 2nd-largest delay. NumPy-style interpolation would give
   131.97 ms instead of 151.16 ms for E1.1. Recomputing the mean from the raw `scheduling_delays` matches the stored summary
   for all 12 files.
4. **One run per condition.** The 12 `results/phase1` runs started between 2026-04-01 14:10 and 14:23 UTC
   (`started_at`). That is just after MONET commit `d547cd7` (14:08 UTC), which added the QLM virtual-queue re-insertion fix.
   Earlier attempts and smoke tests (`supplementary/conversational_qlm_early_runs/`, 13:46–14:09 UTC) are not used by the paper.
   In most of their workloads only 1–5 requests were dispatched.
5. The notebook's saved outputs predate packaging: its "All plots saved to" line shows the original
   `MONET/analysis/plots` location (path redacted).
6. **One request in flight.** `Queue.run_queue` awaits each blocking `worker.add_request` (an OpenAI
   `completions.create` call) before it dispatches the next request. The recorded `backpressure_samples`
   (`vllm:num_requests_running + waiting + swapped`, sampled every 0.25 s) never exceed 1.0 in any of the 12 runs.
   The plateau near 4.8 req/s at 5 and 16 req/s is therefore the rate of this serial client (mean gap between dispatches
   about 208-210 ms in E1.7/E1.8), not a measured GPU limit.
7. **Output length.** `qlm/queue/worker.py` calls `completions.create(model=..., prompt=...)` without `max_tokens`.
   vLLM's OpenAI-compatible completions endpoint defaults to 16 output tokens (`max_tokens: Optional[int] = 16` in
   `CompletionRequest`, e.g. `vllm/entrypoints/openai/protocol.py` of the vllm-continuum base commit), so outputs were
   most likely capped at 16 tokens. The Phase-1 vLLM version is not recorded, and the JSONs store no output lengths.
