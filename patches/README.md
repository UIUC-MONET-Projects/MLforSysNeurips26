# Patches against public upstream packages

The team's working repository (called "MONET" below) vendored four public packages as plain folders.
This artifact does not ship them. Each team modification is a patch against the exact upstream commit
the vendored copy came from.

| Package | Upstream | Base commit | Licence (upstream) | Patch | Files changed |
|---|---|---|---|---|---|
| QLM | https://github.com/QLM-project/QLM | `eea5b622e2c4c6abd705876880f50014c4d9d0d1` (2025-01-16, "Fix README.md") | Apache-2.0 | `QLM.patch` | 17 (7 modified, 10 added) |
| HyperAgent | https://github.com/FSoft-AI4Code/HyperAgent | `c3092f2601ab3bf7f890fac2cd5b1290d3f59256` (2024-11-07, "Create logo_app.svg") | Apache-2.0 | `HyperAgent.patch` | 4 (3 modified, 1 added) |
| vllm-continuum | https://github.com/Hanchenli/vllm-continuum | `316a58794a6ff86b216e579b74fd56ed0c5a911f` (2026-03-20 UTC, "Refactor README content for better readability") | Apache-2.0 | `vllm-continuum.patch` | 3 (3 modified) |
| MAST | https://github.com/multi-agent-systems-failure-taxonomy/MAST | `a70542e541b2104ef8fcd785778179e173fb8d70` (2025-07-23, "Update README.md") | no LICENSE file in the repository (GitHub reports none) | none, no team changes | 0 |

Other external code the artifact depends on, also not shipped:

| Dependency | Upstream | Pinned commit | Used by | Changes |
|---|---|---|---|---|
| pretty-plots | https://github.com/raginigupta6/pretty-plots | `15c2e83ce94502e10719bc9099da3530bd469c6c` | `conversational_qlm/generate_phase1_pretty_plots.py` (imports `utils`) | none. The checkout found next to MONET was clean at this commit. No LICENSE file. |

## Apply

From the repository root:

```bash
mkdir -p third_party && cd third_party
git clone https://github.com/QLM-project/QLM.git
git -C QLM checkout eea5b622e2c4c6abd705876880f50014c4d9d0d1
git -C QLM apply ../../patches/QLM.patch

git clone https://github.com/FSoft-AI4Code/HyperAgent.git
git -C HyperAgent checkout c3092f2601ab3bf7f890fac2cd5b1290d3f59256
git -C HyperAgent apply ../../patches/HyperAgent.patch

git clone https://github.com/Hanchenli/vllm-continuum.git
git -C vllm-continuum checkout 316a58794a6ff86b216e579b74fd56ed0c5a911f
git -C vllm-continuum apply ../../patches/vllm-continuum.patch

# MAST is unmodified. It is only needed for the HyperAgent traces (about 680 MB repository).
git clone https://github.com/multi-agent-systems-failure-taxonomy/MAST.git
git -C MAST checkout a70542e541b2104ef8fcd785778179e173fb8d70
cd ..

# pretty-plots must sit at <repo root>/pretty-plots (generate_phase1_pretty_plots.py looks there)
git clone https://github.com/raginigupta6/pretty-plots.git
git -C pretty-plots checkout 15c2e83ce94502e10719bc9099da3530bd469c6c
```

`third_party/` and `pretty-plots/` are listed in `.gitignore`.

## How the base commits were identified and the patches produced

* The upstream URLs come from the `.git_REMOVED/config` files left in the vendored copies (QLM and MAST),
  from the vendored README and pyproject (vllm-continuum: "vLLM with Continuum Scheduling"; `gh search repos
  vllm-continuum` returns `Hanchenli/vllm-continuum`, "Preview Code for Continuum Paper"), and from the task
  description (HyperAgent).
* For every commit on every ref of each upstream clone, every file's git blob id was compared with the vendored
  copy, using `git hash-object --no-filters` on the MONET working tree and `git ls-tree` on the MONET commit
  that imported the package. These paths were excluded: `.git*`, `.venv*`, `__pycache__`, `*.egg-info`,
  `.DS_Store` and public data (`QLM/data/ShareGPT_V3_unfiltered_cleaned_split.json`). The base is the commit
  with the fewest differing paths:
  * **QLM**: the upstream repository has 2 commits. At import (MONET `d14c779`), the vendored tree differs from
    `eea5b62` in 16 paths (6 modified, 10 added, 0 missing) and from `388b720` in 17. The current tree differs
    from `eea5b62` in 17 paths. `data/README.md` and `LICENSE` are identical.
  * **HyperAgent**: 4 differing paths at `c3092f2` and 132 identical: 131 compared files plus
    `src/hyperagent/tools/tree-sitter/python.so`, which was checked separately because MONET ignores `*.so`. That compares
    with 5 differing paths at `4dfbd9a` and at least 6 at every other commit. The tree imported in MONET `ec7f4e7` gives the same result.
  * **vllm-continuum**: the tree imported in MONET `55fc0c8` is identical to `316a587`: 0 of 3,232 paths differ.
    `971b267` and `3761e57` each differ in 1 path, and the later upstream dependabot commits in 1 to 2 paths. The current
    tree differs from `316a587` in exactly 3 files. `continuum_exp/`, `test_scripts/` and `mini-swe-agent/`
    are upstream content, identical to `316a587`, and are therefore not team code.
  * **MAST**: all 13,373 files are identical to `a70542e` (14 top-level files plus 13,359 files under `traces/`), so there is no patch.
* Patches were produced by checking out the base commit, copying the vendored MONET working tree over it with
  the same exclusions, then running `git add -A` and `git diff --cached --binary --full-index <base>`.
  `core.fileMode=false` was set, so permission-bit differences are ignored. Verification: `git apply --check`
  succeeds for each patch on a fresh checkout of its base commit. After applying, `diff -r` against the vendored
  MONET copy (same exclusions) shows no differences except one intentional redaction in `QLM/qlm/config.yaml`, described below.

## QLM.patch (team changes used by the paper's conversational experiments)

These changes are first recorded in MONET commit `d14c779` (2026-03-30, "Initial MONET repository"), which
already contained the added files and the edits to `config.py`, `config.yaml`, `queue.py`,
`virtual_queue_engine.py`, `scheduler.py` and `requirements.txt`. Git records no authorship before that import.
Later edits are in MONET commits `689ad8b` (queue.py, config.yaml), `2f9ae62` and `0b7eee6` (worker.py),
`b0200b1` (queue.py) and `d547cd7` (virtual_queue_engine.py). All MONET commits are by Neil Teje.

| File | Change |
|---|---|
| `benchmarks/workload_driver.py` (new) | Workload driver used for every Phase-1 run. It controls arrival rate, bursts, concurrent users, dataset and prompt-length bucket. It pushes requests into QLM's `Queue` and records metrics. |
| `benchmarks/lp_smoke_test.py` (new) | Smoke test for QLM's LP (Gurobi) scheduler path. |
| `docs/WORKLOAD_SENSITIVITY_EXPERIMENTS.md` (new) | Design notes on the parameters and metrics of the workload-sensitivity experiments. |
| `qlm/workload/__init__.py`, `datasets.py`, `metrics.py` (new) | ShareGPT / Hugging Face prompt loaders with short/medium/long buckets. `ExperimentMetrics` defines scheduling delay, queue-length sampling, backpressure, and the p50/p99 formulas. |
| `qlm/__init__.py`, `qlm/endpoints/__init__.py`, `qlm/queue/__init__.py`, `qlm/scheduler/__init__.py` (new, empty) | Make the sub-packages importable. |
| `qlm/config.py` | Removes unused vLLM imports. |
| `qlm/config.yaml` | `model_swap_time` 100 → 10. Sets Gurobi WLS `access_id`/`secret_key`; **redacted here** (see below). `license` stays `NULL`. |
| `qlm/queue/queue.py` | Adds a dispatch callback and `get_queue_length()` for metrics. Calls `get_backpressure()` in a thread. Sleeps 10 ms when nothing was dispatched, so producer coroutines can run. Drops the `CancelledError` handler. |
| `qlm/queue/virtual_queue_engine.py` | Scheduler policy comes from env `QLM_SCHEDULER_POLICY` (default `edf`). Re-inserts an emptied group into a virtual queue when a new request arrives for it; per the code comment, requests were otherwise silently dropped. Adds `get_queue_length()`. |
| `qlm/queue/worker.py` | Uses the configured worker address instead of `localhost`. Returns 0.0 backpressure when the metric is missing or unreadable (previously infinite backpressure). |
| `qlm/scheduler/scheduler.py` | Fixes in the LP path: `model_swap_time` attribute, `*_bimap` variable names, `deepcopy` fallback, continuous/binary variable types, Gurobi WLS options only when fully configured, returns the EDF result when the LP fails. |
| `requirements.txt` | Comments out the `mkl-service`, `triton`, `xformers` and `xgrammar` pins. |

**Redaction.** In MONET, `QLM/qlm/config.yaml` contains a Gurobi WLS `access_id`/`secret_key` value; the same UUID appears in both fields. In
`QLM.patch` the two added lines read `REDACTED_GUROBI_WLS_ACCESS_ID` / `REDACTED_GUROBI_WLS_SECRET_KEY`.
Behaviour is unchanged: `license: NULL`, and `scheduler.py` passes WLS options only when access id, secret
and licence are all set. The original value is still in MONET's git history.

## HyperAgent.patch (live HyperAgent → vLLM-Continuum path; no paper figure uses it)

Recorded in MONET commit `ec7f4e7` (2026-04-28, Neil Teje). The import already contained these changes.

| File | Change |
|---|---|
| `src/hyperagent/continuum.py` (new) | Hooks the OpenAI SDK so every chat completion carries Continuum scheduling metadata (`job_id`, `this_func_call`, `is_last_step`) and per-request usage and latency go to a metrics JSON. Also builds one OpenAI-compatible LLM config for all HyperAgent roles. |
| `src/hyperagent/agents/llms.py` | `LocalLLM` uses `HYPERAGENT_CONTINUUM_BASE_URL/_MODEL/_API_KEY` when `HYPERAGENT_CONTINUUM_ENABLED` is set (otherwise the original Together API). |
| `src/hyperagent/pilot.py` | Passes `continuum_job_id` / `continuum_metrics_path` through and enables the hook. |
| `scripts/run_swe_bench.py` | `--backend continuum`, `--continuum_base_url/_model/_metrics_folder`, `--instance_ids` filter, and a per-instance metrics path. |

How to run it is in `supplementary/live_hyperagent_continuum/README.md` (MONET's top-level README).
MONET's output folders for this path (`results/live_hyperagent_{stock,continuum}/`) contain only empty directories.

## vllm-continuum.patch (no paper figure uses it)

| File | Change | MONET commit |
|---|---|---|
| `pyproject.toml` | `[tool.setuptools_scm] search_parent_directories = true`, to allow installing from a vendored sub-folder | `097f11a` (2026-04-17) |
| `setup.py` | `get_version(..., relative_to=__file__, root=ROOT_DIR)`, same purpose | `b93543e` (2026-04-17) |
| `vllm/v1/core/estimate_with_func.py` | `ToolCallParser` also recognises Python-style `tool._run(` calls in fenced blocks. `ToolCallEstimator.request_finished` keeps a client-supplied `this_func_call` | `975cf9f` (2026-04-29) |

All three are by Neil Teje. The `estimate_with_func.py` change post-dates every replay output in
`agentic_continuum/hyperagent-replay/replays-two/` (last request 2026-04-17 05:18 UTC).

## Large generated or data files inside the vendored trees (not shipped)

* `QLM/data/ShareGPT_V3_unfiltered_cleaned_split.json` (672,837,942 bytes, SHA-256
  `35f0e213ce091ed9b9af2a1f0755e9d39f9ccec34ab281cd4ca60d70f6479ba4`): public dataset. Download URL (from the team's
  `validate_setup.sh`): https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered/resolve/main/ShareGPT_V3_unfiltered_cleaned_split.json
* `QLM/.venv311/` (local Python 3.11.12 virtualenv, about 1.8 GB) and `QLM/qlm.egg-info/`: environment artefacts.
* `MAST/traces/` (13,359 files, about 1.3 GB): public MAST traces, identical to upstream `a70542e`.
* `vllm-continuum/continuum_exp/` (`analyze.py` plus small SWE-bench Llama-70B `results.json`/`verification.json`)
  is upstream content, identical to `316a587`, not team data.
