# Agentic workloads: HyperAgent trace replay ("vLLM vs Continuum")

Paper: Section 3.2 (setup), Sections 4.2–4.4, Figure 1 (`fig:prefill`, `result1 (1).jpeg`), Figure 2
(`fig:cache_hits`, `result2 (1).jpeg`), Figure 3 (`fig:jct`, `result3.jpeg`), Appendix B Table 3 (`tab:agent_jct`).

| Path | What | Source in MONET | Authors (git) |
|---|---|---|---|
| `hyperagent-replay/` | Python package: extract HyperAgent trajectories into LLM turns, replay them against an OpenAI-compatible vLLM endpoint (baseline), replay with exact-repeat reuse, evaluate, analyze | `hyperagent-replay/` working tree (nested repo, origin https://github.com/AdityaKunte18/hyperagent-replay, HEAD `825ed8e373df9f43a57f0b0809b59c074a86eed5`) | Aditya Kunte (all origin commits). Local uncommitted edits were recorded in MONET commits `3068f9c` and `975cf9f` by Neil Teje |
| `hyperagent-replay/extracted-two/` | Extracted replay inputs (24 traces + manifest), derived from MAST `traces/HyperAgent/*_human.json` | same | Aditya Kunte |
| `hyperagent-replay/replays-two/` | Raw replay outputs for the 10 paper traces: `*.baseline.replay.json`, `*.reuse.replay.json`, `*scheduler_timestamps.json`, `vllm.log` | same | Aditya Kunte |
| `hyperagent-replay/reuse-analysis/` | `ha-trace-analyze-reuse` output over `replays-two` (CSV, JSON, SVG) | same | Aditya Kunte |
| `hyperagent-replay/evals/` | One early `ha-trace-eval` output (astropy-12907). Not used by the paper | same | Aditya Kunte |
| `results/data/` | `instance_summary.csv`, `full_trace_per_turn.csv`, `agent_turn_summary.csv` | `results/data/` | not tracked in git, no authorship record |
| `results/plots/` | 27 PNGs + `summary_table.csv`. **07, 20 and 16 are the paper's Figs. 1, 2 and 3** | `results/plots/` | not tracked in git, no authorship record |

Left out of `hyperagent-replay/`:
* `trajectories/`: copies of public MAST traces. 27 files are byte-identical to MAST `a70542e` `traces/HyperAgent/`;
  `sphinx-doc__sphinx-8435_human.json` is an empty placeholder.
* `extracted/`: an older extraction. Its 24 overlapping files are byte-identical to `extracted-two/`; its 3 extra traces
  are not used by the paper.
* `.git/` and `__pycache__/`.

To restore the trajectories: copy `MAST/traces/HyperAgent/*_human.json` from a MAST checkout at `a70542e` (see `patches/README.md`)
into `hyperagent-replay/trajectories/`. To restore `extracted/`: run `ha-trace-batch-extract hyperagent-replay/trajectories --output-dir hyperagent-replay/extracted`.

## Pipeline behind Figures 1–3

```
MAST traces/HyperAgent/<id>_human.json
  └─ ha-trace-batch-extract ─────────────► hyperagent-replay/extracted-two/<id>_human.extracted.json
       ├─ ha-trace-batch-replay ─────────► replays-two/<id>_human.baseline.replay.json   ("stock vLLM")
       └─ ha-trace-replay-reuse ─────────► replays-two/<id>_human.reuse.replay.json      ("Continuum" in the paper)
            └─ ha-trace-analyze-reuse ───► reuse-analysis/pairwise_comparison.csv (+ other CSV/SVG)
  [code not present anywhere in MONET] ──► results/data/*.csv and results/plots/*.png
  [manual crop / JPEG export, no code] ──► MLSYS2/result1 (1).jpeg, result2 (1).jpeg, result3.jpeg
```

Evidence for the last two steps:
* `results/plots/summary_table.csv` equals `reuse-analysis/pairwise_comparison.csv` on all 140 shared values.
* `results/data/full_trace_per_turn.csv` matches the replay JSONs turn by turn for `stock_vllm` (930 rows) and,
  for `continuum`, in `prompt_tokens` and `cache_hit` (caveat 4 covers latencies).
* `result3.jpeg` has the same pixel size as `16_cumulative_jct_waterfall.png` (1548×638). `result1 (1).jpeg` and `result2 (1).jpeg`
  are `07_prefill_decode.png` and `20_running_hit_rate.png` with their titles cropped off, resized to 1600 px wide.
* A Spotlight (`mdfind`) search of the authoring machine for these file names returned only the PNG itself. `results/plots_v3/KEY_FINDINGS.md` cites
  `results/generate_plots_v3_simulation.py`, which also does not exist.

## Regenerating

```bash
pip install -e agentic_continuum/hyperagent-replay
cd agentic_continuum/hyperagent-replay
# reuse-analysis/ from the raw replays (compare the output with the shipped reuse-analysis/)
ha-trace-analyze-reuse --baseline-glob "replays-two/*.baseline.replay.json" \
  --reuse-glob "replays-two/*.reuse.replay.json" --output-dir /tmp/reuse-analysis-check
```

Checked during packaging: running this on the shipped `replays-two/` with the shipped code reproduced all 21 files of
`reuse-analysis/` byte for byte (Python 3.14; `openai` was stubbed because `analyze_reuse` never calls it).

The plotting code for Figs. 1–3 is missing. The numbers they show can be recomputed with the standard library:

```python
import csv
rows = list(csv.DictReader(open("agentic_continuum/hyperagent-replay/reuse-analysis/pairwise_comparison.csv")))
for r in rows:   # Fig. 1: prompt ("prefill") tokens avoided; Fig. 2: final hit rate
    print(r["instance_id"], int(float(r["baseline_total_prompt_tokens"]) - float(r["reuse_total_prompt_tokens"])),
          round(float(r["reuse_cache_hit_pct"]), 1))
rows.sort(key=lambda r: -float(r["baseline_wall_solve_time_s"]))   # Fig. 3 order: largest job first
cb = cr = 0.0
for r in rows:
    cb += float(r["baseline_wall_solve_time_s"]) / 60; cr += float(r["reuse_wall_solve_time_s"]) / 60
    print(r["instance_id"], round(cb, 2), round(cr, 2))
```

Output from the shipped data: prompt tokens avoided are 2,712,305 (astropy-14365), 448,003 (matplotlib-24334),
277,865 (astropy-6938), 101,805 (astropy-12907), 11,512 (django-11742), 4,958 (matplotlib-24265), 4,160 (matplotlib-18869),
and 0 for the other three. Final hit rates are 43.9 / 40.5 / 35.9 / 31.3 % for astropy-14365 / astropy-6938 / matplotlib-24334 /
astropy-12907. Cumulative wall time ends at **171.02 min (baseline) vs 111.49 min (reuse), a 34.8 % reduction**. The series in
largest-first order is 77.23, 108.03, 128.87, 142.99, 149.57, 155.65, 160.44, 164.60, 168.47, 171.02 (baseline) and
41.61, 62.81, 75.35, 84.39, 90.73, 96.33, 101.16, 105.37, 108.97, 111.49 (reuse).

## Re-running the replays (GPU)

Per `hyperagent-replay/README.md`: Python 3.11, `Qwen/Qwen2.5-Coder-14B-Instruct` on one 46 GB A40 (NCSA Delta `gpuA40x4`),
`vllm serve ... --max-model-len 32768`. The replay settings recorded in every `replays-two/*.replay.json` are
temperature 0.0, seed 0, `max_completion_tokens` 512, `context_mode` per_agent, `max_reference_chars` 4000 and
`delay_policy` heuristic. `max_model_len` is 32768 in the astropy-12907/14365 baselines and `null` in all other files.
Commands are in `hyperagent-replay/README.md` (Phase 2, "Reuse-aware replay", "Reuse Analysis"). The replays were produced
2026-04-08 to 2026-04-17 (last request 05:18 UTC) with the origin code of that period. The working-tree edits shipped here came
later (MONET `3068f9c`, 2026-04-17 16:00 UTC, and `975cf9f`, 2026-04-29). They only add opt-in flags
(`--engine-mode continuum`, `--reset-prefix-cache-between-traces`, `ha-trace-compare-regime-a`) and extra output fields.
Their defaults keep the stock request payload.

## Caveats for auditors

1. **What "Continuum" means in Figs. 1–3.** The "Continuum" series is computed from `*.reuse.replay.json`. Every one of
   those files records `settings.reuse_mode = "exact_repeat_full_stage_memoization"`. That mode is implemented client-side
   in `replay_reuse.py`; the package README says it "stays on top of `vllm serve`: it does not modify vLLM internals ...
   when it sees an exact repeated stage it reuses the prior assistant response instead of sending a new request to vLLM".
   MONET's own plan (`supplementary/regime_a_delta/RUN_ON_DELTA.md`) says "Cells A/B come straight from `replays-two/`",
   where B is "stock vLLM, sub-agent reuse". The vllm-continuum cells C/D are "what we run on the GPU node".
   The replay files do not record the server URL or engine, so the server used for the reuse runs could not be verified.
2. **No vllm-continuum outputs exist in MONET.** MONET has no `results/regime_a/`, and MONET's
   `results/live_hyperagent_{stock,continuum}/` contain only empty `metrics/`, `patches/` and `server_events/` directories.
3. **Baseline server configuration.** The only server log, `replays-two/vllm.log`, covers the 2026-04-08 baseline runs of
   astropy-12907 and astropy-14365. It shows stock vLLM 0.18.1 with `enable_prefix_caching=True`; the logged "Prefix cache hit rate" reaches
   95.2 % (647 log lines). The non-default args are only model, host and `max_model_len` 32768, with no scheduling-policy flag.
4. **`results/data` "continuum" latencies do not match any measured run.** For `condition == continuum`,
   `full_trace_per_turn.csv` matches `*.reuse.replay.json` in `prompt_tokens` and `cache_hit`, but `request_latency_s`
   differs in 926 of 930 rows. Over the 626 executed turns, the CSV/replay ratio has median 0.629 (range 0.465–1.101);
   for example, astropy-12907 turn 0 is 13.4626 s in the CSV and 18.4597 s in the replay. Cache-hit turns have small non-zero
   CSV latencies where the replay records 0.0. `instance_summary.csv` "continuum" `total_wall_time_s` sums to 77.25 min,
   against 111.49 min measured. Fig. 3 matches the measured values (pairwise_comparison / summary_table), not these.
   No code in MONET produces these CSVs.
5. **Conditions differ beyond reuse.** Baseline and reuse runs of the same trace ran on different days (baselines
   2026-04-08 and 04-16, reuse runs 04-14 to 04-17, from `request_arrival_time`). Context budgeting also differs for the
   two largest traces. astropy-14365: baseline 155 trimmed turns, 0 context retries (`max_model_len` 32768); reuse
   46 trimmed turns, 335 context-retry events (`max_model_len` null). astropy-12907: 28 vs 10 trimmed turns, 0 vs 31 retries.
6. **"Prefill tokens"** in Fig. 1 are summed `usage.prompt_tokens` of the requests that were actually sent. The reduction
   equals the prompt tokens of turns served from the client-side cache, plus any budgeting differences (caveat 5).
7. **Paper numbers that do not match the data.** The paper states a cumulative completion time of 162 → 105 min. The data
   gives 171.02 → 111.49 min (Fig. 3 itself ends near 171 / 112). Table 3's values (9 rows, no astropy-14365, ending 162 / 105)
   appear in no file in MONET and do not match the recomputed series above.
8. Fig. 2's running hit rate is labelled "window avg" in the uncropped PNG. The window size cannot be recovered because the code is missing.
9. Licence: MAST has no LICENSE file. `extracted-two/` and the `request_messages` inside `replays-two/` contain MAST-derived
   text (including SWE-bench issue text that quotes third-party home-directory paths, e.g. in the seaborn-3407 and pylint-6506
   inputs; these come verbatim from MAST and were left unchanged).
