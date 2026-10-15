# Code and data for "From Conversational Chats to Agents: Workload-Dependent Bottleneck Shifts in LLM Serving"

This repository holds the code and data the team wrote for the paper *"From Conversational Chats to Agents:
Workload-Dependent Bottleneck Shifts in LLM Serving"*. The paper source is `MLSYS2/neurips_2026.tex` in the team's working
repository; its header calls it a "NeurIPS ML for Systems workshop extended abstract", and a commented-out author block lists
Ragini Gupta, Neil Teje and Klara Nahrstedt (UIUC). The paper compares a common vLLM baseline against two serving
mechanisms. (1) QLM's queue-aware, SLO-oriented scheduling, on six ShareGPT conversational workloads with
Llama-3.2-1B-Instruct. (2) "Continuum"-style cross-turn reuse, on ten HyperAgent software-engineering traces from MAST, replayed
against Qwen2.5-Coder-14B-Instruct. Everything here was extracted from the team's working repository, called **MONET** below.
Public upstream packages (QLM, HyperAgent, vllm-continuum, MAST, pretty-plots) are not included: they are referenced by URL
and pinned commit, and the team's modifications ship as patches. Paper sources, drafts, planning notes and public datasets are
also left out.

**Read the "Known gaps" section before auditing the paper's agentic results.**

## Layout

```
README.md                  this file
PROVENANCE.md              every shipped file -> MONET source path, git authors, packaging changes
conversational_qlm/        Experiment 1: vLLM vs QLM on ShareGPT (paper Table 1, Table 2, Figs. 4-6)
  scripts/                   phase1_runner.sh (the 12 runs), validate_setup.sh
  results/phase1/            raw metrics JSON of the 12 runs used in the paper
  phase1_sharegpt.ipynb      analysis notebook -> plots/ (summary_statistics.csv, summary_table.tex, PNGs)
  generate_phase1_pretty_plots.py  -> plots_pretty/ (the paper's appendix figures)
agentic_continuum/         Experiment 2: HyperAgent trace replay (paper Figs. 1-3, Table 3)
  hyperagent-replay/         replay/analysis package (Aditya Kunte) + extracted inputs, raw replays, reuse analysis
  results/                   per-instance/per-turn CSVs and the plots behind Figs. 1-3
patches/                   QLM.patch, HyperAgent.patch, vllm-continuum.patch + README (upstream URLs, base commits, licences)
supplementary/             team code/data the paper does NOT use (SLO framework, Regime-A plan, early runs, simulated plots)
```

Size: 235 files, about 118 MB, nearly all of it raw replay JSON. The largest file is 37.6 MB
(`agentic_continuum/hyperagent-replay/replays-two/astropy__astropy-14365_human.reuse.replay.json`); none exceeds 50 MB.

## Paper artifact → code and data

Paper file names are those in `MLSYS2/`. "Status" uses: **reproducible** (producing code and input data are both
here); **data-only** (data and the rendered image are here, the plotting code is not); **code-missing** (no producing
code or source data found anywhere in MONET).

| Paper artifact | Producing code (this repo) | Data (this repo) | Status | Notes |
|---|---|---|---|---|
| Table 1 `tab:chat` (main text) | `conversational_qlm/phase1_sharegpt.ipynb` (summary cell; throughput as in the plot-3 cell) | `conversational_qlm/results/phase1/*.json`, `conversational_qlm/plots/summary_statistics.csv` | reproducible | Values were typed into the tex. All match the data after rounding; see `conversational_qlm/README.md` |
| Table 2 `tab:full_results` (`\input{summary_table.tex}`) | notebook cell 19 (`to_latex`) | `conversational_qlm/plots/summary_table.tex` | reproducible | Byte-identical to `MLSYS2/summary_table.tex` |
| Fig. 4 `fig:app_delay` (`plot1_scheduling_delay_baseline.png`) | `conversational_qlm/generate_phase1_pretty_plots.py` | `conversational_qlm/results/phase1/{vllm,qlm}_baseline_mixed.json`; output `conversational_qlm/plots_pretty/plot1_*.png` | reproducible | Output byte-identical to the paper's file. Needs pretty-plots at `15c2e83` (not shipped) |
| Fig. 5 `fig:queue_regimes` (`plot2_queue_length_over_time.png`) | same script | `conversational_qlm/results/phase1/*` (baseline, high-rate, bursty, multi-user); `conversational_qlm/plots_pretty/plot2_*.png` | reproducible | The paper version has its panel titles removed by hand (no code) |
| Fig. 6 `fig:app_prompt` (`plot4_prompt_length_sensitivity.png`) | same script | `conversational_qlm/results/phase1/*` (short, mixed, long); `conversational_qlm/plots_pretty/plot4_*.png` | reproducible | The paper version is cropped by hand (titles removed) |
| Fig. 1 `fig:prefill` (`result1 (1).jpeg`) | **missing**. Upstream data step: `ha-trace-replay` / `ha-trace-replay-reuse` / `ha-trace-analyze-reuse` | `agentic_continuum/results/plots/07_prefill_decode.png` (uncropped source image), `agentic_continuum/results/data/instance_summary.csv`, `agentic_continuum/hyperagent-replay/reuse-analysis/pairwise_comparison.csv`, raw `agentic_continuum/hyperagent-replay/replays-two/` | data-only | Token totals match the replay JSONs exactly. "Continuum" = client-side exact-repeat reuse replay; see Known gaps 1–2 |
| Fig. 2 `fig:cache_hits` (`result2 (1).jpeg`) | **missing** (same upstream data step) | `agentic_continuum/results/plots/20_running_hit_rate.png`, `agentic_continuum/results/data/full_trace_per_turn.csv` (`cache_hit`), `agentic_continuum/hyperagent-replay/replays-two/*.reuse.replay.json` | data-only | Final rates 31/44/41/0/0/7/5/17/36/0 % match the data. "Window avg" size unknown |
| Fig. 3 `fig:jct` (`result3.jpeg`) | **missing** (same upstream data step) | `agentic_continuum/results/plots/16_cumulative_jct_waterfall.png` (same pixel size), `agentic_continuum/results/plots/summary_table.csv` (= `pairwise_comparison.csv`) | data-only | Data: 171.02 → 111.49 min (−34.8 %). The paper text says 162 → 105 min |
| Table 3 `tab:agent_jct` (appendix) | none | none | code-missing | Its 9 rows (75…162 / 40…105, no astropy-14365) appear in no MONET file and do not match the recomputed series in `agentic_continuum/README.md` |

Numbers quoted in the text: p99 151.2 → 47.4 ms and 110.4 → 50.2 ms; queue 11.08 → 9.19 and 24 → 16; 670+ queue (674/672);
about 4.8 req/s; 2.7M / 448K / 278K / 102K prefill tokens; 44 / 41 / 36 % hit rates. All are reproducible from the shipped data
with the snippets in the two component READMEs. The 35 % reduction is consistent with the data (34.8 %). The
162 / 105-minute totals are not.

## Environment

* Python 3.11. The notebook metadata records 3.11.12. hyperagent-replay requires >=3.10,<3.13.
* `conversational_qlm/requirements.txt`: analysis and plotting. Versions are those observed in MONET's local
  `QLM/.venv311`; unverified ones are marked.
* `agentic_continuum/requirements.txt`: `pip install -e agentic_continuum/hyperagent-replay` (only `openai>=1.30.0`).
* `supplementary/continuum_slo_framework/requirements.txt` (team file, unpinned).
* GPU experiments: a vLLM server (Phase 1: `unsloth/Llama-3.2-1B-Instruct`, one NVIDIA L4 per the team's earlier write-up;
  Phase 2: `Qwen/Qwen2.5-Coder-14B-Instruct` on one 46 GB A40 per hyperagent-replay's README; `vllm.log` records vLLM 0.18.1,
  but only for the 2026-04-08 baseline runs).

## Upstream packages and patches

`patches/README.md` has the exact clone, checkout and `git apply` commands. Each patch was verified with
`git apply --check` on a fresh checkout of its base commit. Upstream licences are listed there.

| Package | Base commit | Patch | Needed for |
|---|---|---|---|
| QLM (Apache-2.0) | `eea5b622e2c4c6abd705876880f50014c4d9d0d1` | `patches/QLM.patch` (adds the workload driver + metrics used for all Phase-1 data) | re-running Experiment 1 |
| HyperAgent (Apache-2.0) | `c3092f2601ab3bf7f890fac2cd5b1290d3f59256` | `patches/HyperAgent.patch` | live HyperAgent path only (no paper figure) |
| vllm-continuum (Apache-2.0) | `316a58794a6ff86b216e579b74fd56ed0c5a911f` | `patches/vllm-continuum.patch` | Continuum server (no paper figure uses its outputs) |
| MAST (no licence file) | `a70542e541b2104ef8fcd785778179e173fb8d70` | none (unmodified) | HyperAgent traces |
| pretty-plots (no licence file) | `15c2e83ce94502e10719bc9099da3530bd469c6c` | none | `generate_phase1_pretty_plots.py` styling |

## Re-running and regenerating

* Experiment 1 (GPU) and its tables/figures: `conversational_qlm/README.md`. The notebook and the plot script read
  `conversational_qlm/results/phase1/` (paths fixed during packaging). Re-runs should set `RESULTSDIR` to a new directory.
* Experiment 2 (GPU) and the reuse analysis: `agentic_continuum/README.md`. `ha-trace-analyze-reuse` regenerates
  `reuse-analysis/` from the shipped raw replays; during packaging this reproduced all 21 files byte for byte. Figs. 1–3 can only be checked numerically (snippet provided) because their
  plotting code is missing.
* Public data not committed: ShareGPT (`ShareGPT_V3_unfiltered_cleaned_split.json`, URL and SHA-256 in
  `patches/README.md`); MAST HyperAgent traces (MAST `a70542e`, `traces/HyperAgent/*_human.json`); model weights from
  Hugging Face.

## Known gaps (evidence in the component READMEs)

1. **The agentic "Continuum" results come from a client-side reuse replay, not from a vllm-continuum server run.** Every
   `agentic_continuum/hyperagent-replay/replays-two/*.reuse.replay.json` records
   `reuse_mode = exact_repeat_full_stage_memoization`, implemented in
   `agentic_continuum/hyperagent-replay/src/hyperagent_replay/replay_reuse.py` on top of `vllm serve`. MONET's own plan says cells A/B
   (stock vLLM, ± sub-agent reuse) "come straight from `replays-two/`". The only server log shows stock vLLM 0.18.1 with
   prefix caching on (hit rate up to 95.2 %).
2. **No vllm-continuum or live-HyperAgent outputs exist in MONET.** MONET's `results/live_hyperagent_*` are empty directories;
   there is no Regime-A output.
3. **Plotting code for Figs. 1–3 and the generator of `agentic_continuum/results/` are missing.** In those CSVs the
   `continuum` per-turn latencies differ from the measured replays (median ratio 0.629). Fig. 3 follows the measured values.
4. **Table 3 and the 162 → 105 min totals cannot be reproduced** from any file. The data gives 171.02 → 111.49 min.
5. **Phase 1: nothing distinguishes the "vLLM" runs from the "QLM" runs.** The runner issues identical commands for both, and
   the driver always goes through QLM's queue. p99 is a nearest-rank value: the 2nd-largest of 120 delays.
6. Paper figures 1–3 and 5–6 were cropped or converted by hand. The paper PDF/tex and figure files are not shipped.
7. Baseline and reuse replays of a trace ran on different days with different context-budget settings (max_model_len
   32768 vs null for the two largest traces).
8. Credentials: a Gurobi WLS id/secret in MONET's `QLM/qlm/config.yaml` is redacted in `patches/QLM.patch`. It remains in
   MONET's git history.

## Packaging checks (run before the commit)

* `python3 -m py_compile` on all 19 Python files: pass. The notebook parses as nbformat-4 JSON.
* `git apply --check` of each patch on a fresh checkout of its base commit: pass. After applying, the result equals the
  vendored MONET copy except the redacted `qlm/config.yaml`.
* Regex secrets / machine-detail scan (HF/OpenAI/Anthropic/GitHub/AWS/W&B/Slack keys, Gurobi WLS, passwords, private keys,
  home paths, NCSA Delta allocations/paths/hosts, private IPs, team user ids): 0 unreviewed hits. 28 reviewed hits are
  third-party home paths quoted from public SWE-bench issues inside MAST traces (`extracted-two/`).
* No file exceeds 50 MB. The largest is 37.6 MB.
* Byte-identity against every commit of the upstream clones (QLM, HyperAgent, vllm-continuum, MAST, pretty-plots): only
  the empty `replay_skip_list.txt` matches (it is an empty file). 97 files under `agentic_continuum/hyperagent-replay/`
  match the team's own origin repository, as intended.
* `conversational_qlm/plots/summary_statistics.csv` re-derived from `results/phase1/*.json` with the notebook's logic: 0 mismatches.
  `ha-trace-analyze-reuse` on the shipped replays reproduces all 21 `reuse-analysis/` files byte for byte.
* The notebook, `generate_phase1_pretty_plots.py` and `supplementary/continuum_slo_framework/simulate_load.py` resolve their
  default data paths in this layout. The simulator was smoke-run with output written outside the repository.
* Every path-like token in the five READMEs resolves to a file in this repo, a MONET path described as such, a file in a
  patched upstream checkout, a directory the instructions create, or a deliberately non-existent/non-path reference.

## Contributors (from git history)

| Component | Contributors |
|---|---|
| `conversational_qlm/`, `patches/QLM.patch`, `patches/HyperAgent.patch`, `patches/vllm-continuum.patch`, `supplementary/regime_a_delta/`, `supplementary/live_hyperagent_continuum/`, `supplementary/conversational_qlm_early_runs/` | Neil Teje (all 23 MONET commits). QLM edits made before MONET's first commit (`d14c779`) have no recorded author |
| `agentic_continuum/hyperagent-replay/` | Aditya Kunte (all 39 commits of https://github.com/AdityaKunte18/hyperagent-replay up to `825ed8e`, under the git identities "AdityaKunte18", "Aditya Kunte" and "Aditya Shreenivas Kunte"). The local edits (Continuum engine mode, `compare_regime_a.py`) were committed to MONET by Neil Teje (`3068f9c`, `975cf9f`) |
| `agentic_continuum/results/`, `supplementary/continuum_slo_framework/`, `supplementary/agentic_results_unused/` | not tracked in git, no authorship record |
| pretty-plots (dependency, not shipped) | GitHub user `raginigupta6` |

## Licence

To be decided by the authors. No licence file is included. Upstream licences are listed in `patches/README.md`.
`hyperagent-replay`'s origin repository has no licence file. MAST, the source of the HyperAgent traces (`extracted-two/` and the
replay prompts are derived from them), has no licence file either.
