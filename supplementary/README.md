# Supplementary: team code and data NOT used in the paper

The paper (`MLSYS2/neurips_2026.tex`) uses nothing in this folder. It is shipped for completeness, so the audit can see
everything the team wrote. Sources are paths in the team's working repository ("MONET"); details are in `../PROVENANCE.md`.

| Folder | What | Source in MONET | Git authorship |
|---|---|---|---|
| `continuum_slo_framework/` | Later exploration: an SLO-aware queue/admission proxy in front of Continuum (`proxy.py`), a discrete-event load simulator (`simulate_load.py`) and plots (`plot_slo.py`). `outputs/` holds **simulated** sweeps | `continuum_slo_framework/` (untracked in git, files dated 2026-05-11). `DISCUSSION_BRIEF.md` (a meeting brief) was left out | none (untracked) |
| `regime_a_delta/` | `RUN_ON_DELTA.md` and `run_regime_a.sh`: plan and driver for the 2×2 "Regime A" matrix (stock vs vllm-continuum × no-reuse vs reuse) on NCSA Delta / RunPod. MONET contains no outputs from it | `monet_research/phase2_mast_continuum/` | Neil Teje (`975cf9f`) |
| `live_hyperagent_continuum/README.md` | How to run live HyperAgent against a vLLM-Continuum server. Needs `patches/HyperAgent.patch` and `patches/vllm-continuum.patch`. MONET's output dirs for it are empty | MONET top-level `README.md` | Neil Teje |
| `conversational_qlm_early_runs/` | Phase-1 attempts and smoke tests from 2026-04-01 13:46–14:09 UTC, all before the 12 paper runs (14:10–14:23 UTC). The `v1_phase1`/`v2_phase1` runs (13:48–14:00 UTC) predate the QLM re-insertion fix commit `d547cd7` (14:08 UTC), and most of their workloads dispatched only 1–5 requests. `v1_phase1/` files are byte-identical to the same-named `v2_phase1/` files. Also `smoke_test.json` and `test_metrics.json` | `monet_research/results/{v1_phase1,v2_phase1,smoke_test.json,test_metrics.json}` | Neil Teje (`04f8583`) |
| `agentic_results_unused/` | `plots_v2/` (5 alternative agentic plots). `plots_v3/` with `KEY_FINDINGS.md` and `simulated_metrics.csv`: a **synthetic extrapolation** to a 3B AWQ model, labelled as such in its own README. `data/live_run_simulated.csv` (**simulated**, per its name; it differs slightly from `agentic_continuum/results/data/full_trace_per_turn.csv`) | `results/plots_v2/`, `results/plots_v3/`, `results/data/live_run_simulated.csv` | none (untracked) |

Notes
* Packaging changed paths in this folder as follows.
  * `continuum_slo_framework/simulate_load.py` now reads its default inputs from `../agentic_continuum/results/data/`
    (path fix, see PROVENANCE). Its README's commands say `continuum_slo_framework/...`; from this repo's root use
    `supplementary/continuum_slo_framework/...`.
  * The simulator's "continuum" backend reads the `continuum` rows of `instance_summary.csv` / `full_trace_per_turn.csv`.
    Those rows carry latencies that differ from the measured replays (see caveat 4 in `../agentic_continuum/README.md`).
  * `regime_a_delta/` commands assume MONET's layout: `hyperagent-replay/`, `vllm-continuum/`, and
    `monet_research/phase2_mast_continuum/run_regime_a.sh`. Here those are `agentic_continuum/hyperagent-replay/`,
    `third_party/vllm-continuum/` (patched) and `supplementary/regime_a_delta/run_regime_a.sh`. Its example input dir
    `hyperagent-replay/extracted` was left out; `extracted-two/` holds the same files for the 24 traces it covers.
  * `live_hyperagent_continuum/README.md` commands (`pip install -e vllm-continuum`, `cd HyperAgent`) refer to the patched
    upstream checkouts, `third_party/vllm-continuum` and `third_party/HyperAgent` here.
* `RUN_ON_DELTA.md` had the NCSA Delta allocation name replaced by `<DELTA_ACCOUNT>`.
