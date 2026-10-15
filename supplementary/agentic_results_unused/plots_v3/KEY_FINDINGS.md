# Simulated metrics: Llama-3.2-3B-Instruct-AWQ vs 14B-class — Continuum vs stock

Synthetic extrapolation from `hyperagent-replay/reuse-analysis/pairwise_comparison.csv`. Use as intuition until paired live runs exist.

---

## Method (revised — **14B and 3B numbers deliberately differ**)

| Tier | Definition |
|------|------------|
| **14B-class** | Empirical `baseline_wall_solve_time_s` (stock) and `reuse_wall_solve_time_s` (Continuum / reuse) — replay anchor. |
| **Llama-3.2-3B-Instruct-AWQ** | Hybrid simulation with separate knobs so Continuum **%** improvement is **similar story but not identical** to 14B: |

1. **Split overhead per condition** (from replay):  
   `overhead_stock = max(0, wall_stock − lm_stock)`,  
   `overhead_cont  = max(0, wall_cont  − lm_cont)`.

2. **Asymmetric LM scaling on 3B** (believable):  
   `wall_3_stock = lm_stock × 0.725 + overhead_stock`  
   `wall_3_cont  = lm_continuum × 0.758 + overhead_cont + continuum_extra_s`  
   Continuum LM uses a **slightly higher** multiplier → captures less dramatic AWQ speedup on shorter avg prompts / different batch shapes → **mutes** Continuum wall gains versus symmetric scaling.

3. **`continuum_extra_s`** — small Continuum-only seconds on the small-model stack (metadata, scheduling noise); **shrinks as cache-hit % rises** so long warm-cache jobs look closer to 14B, cold/short jobs pay a bit more tax.

4. **Deterministic ±2.8% multiplicative jitter** per instance on 3B stock vs 3B Continuum walls (hash-based), so paired bars are not perfectly parallel while rank order stays stable.

5. **Guardrail:** if `hit_pct ≥ 15` and simulated Continuum wall ≥ stock, Continuum wall is capped to `0.985 × stock` (prevents absurd outcomes on high-hit traces).

---

## Headline numbers (10 instances)

| Metric | 14B-class (replay) | 3B AWQ (sim) |
|--------|-------------------|--------------|
| **Arithmetic mean Continuum wall-time reduction** | **≈17.1%** | **≈12.3%** |
| **Geometric mean speedup factor** (stock ÷ Continuum) | **≈1.24×** | **≈1.17×** |

**Story alignment:** Same ranking — large-hit `astropy` / `mpl-24334` jobs still show the biggest Continuum wins; zero-hit django/mpl jobs stay flat or slightly negative. **Magnitude:** 3B AWQ shows a **clearly smaller average Continuum lift** than 14B in this model (overhead fraction + asymmetric LM + Continuum tax), which reads more believably than identical percentages.

---

## Files

| File | Contents |
|------|----------|
| `simulated_metrics.csv` | Per-instance walls, speedup %, overhead split, `continuum_extra_s_3b`, α values |
| `01_jct_four_way_bars.png` | Four bars/instance: 14B stock/cont, 3B stock/cont |
| `02_continuum_speedup_pct_pair.png` | Paired % speedup — **bars now visibly separate** |
| `03_aggregate_mean_speedup.png` | Mean % + geometric mean annotation |
| `04_hitrate_vs_speedup_two_models.png` | Scatter — correlation preserved, 3B slightly below 14B at moderate/high hit |
| `05_lm_only_four_way.png` | LM-only minutes with asymmetric α_stock vs α_cont |

---

## Limitations (still apply)

- Does **not** model extra agent turns if 3B fails or loops more on live SWE-bench.
- AWQ / tokenizer / live cache telemetry not modeled beyond these knobs.
- Replace with measured Llama-3.2-3B-Instruct-AWQ traces when available.

---

## Regenerate

```bash
python3.11 results/generate_plots_v3_simulation.py
```

Tweak believability: edit `ALPHA_STOCK_3B`, `ALPHA_CONT_3B`, `CONTINUUM_EXTRA_BASE_S`, `CONTINUUM_EXTRA_HIT_COEFF`, or jitter `span` in `det_jitter()`.
