#!/usr/bin/env python3
"""
Plot SLO/load-sweep results from simulate_load.py.

Input:
  continuum_slo_framework/outputs/slo_sweep.csv

Outputs:
  continuum_slo_framework/outputs/*.png
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "outputs", "slo_sweep.csv")
DEFAULT_OUTPUT_DIR = os.path.join(HERE, "outputs")


COLORS = {
    "stock_vllm/fcfs": "#4C72B0",
    "stock_vllm/edf": "#5B8FD6",
    "stock_vllm/cache_aware_edf": "#88AADD",
    "stock_vllm/slack_cache": "#A6BDD7",
    "continuum/fcfs": "#DD8452",
    "continuum/edf": "#E39A6A",
    "continuum/cache_aware_edf": "#55A868",
    "continuum/slack_cache": "#2E8B57",
}


def load_rows(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out = {}
            for k, v in r.items():
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    out[k] = v
            rows.append(out)
    return rows


def grouped(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = f"{r['backend']}/{r['policy']}"
        g[key].append(r)
    for vals in g.values():
        vals.sort(key=lambda r: r["arrival_rate_jobs_per_min"])
    return dict(g)


def save(fig: plt.Figure, out_dir: str, name: str) -> None:
    path = os.path.join(out_dir, name)
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  {name}")


def line_plot(
    rows: list[dict[str, Any]],
    *,
    x_col: str,
    y_col: str,
    y_label: str,
    title: str,
    filename: str,
    out_dir: str,
    y_scale: float = 1.0,
    x_label: str = "Arrival rate (jobs/min)",
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for key, vals in grouped(rows).items():
        xs = [v[x_col] for v in vals]
        ys = [v[y_col] * y_scale for v in vals]
        ax.plot(
            xs,
            ys,
            marker="o",
            lw=1.8,
            label=key,
            color=COLORS.get(key),
            alpha=0.9,
        )
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(frameon=False, fontsize=8)
    save(fig, out_dir, filename)


def plot_all(rows: list[dict[str, Any]], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="slo_met_rate",
        y_scale=100.0,
        y_label="SLO attainment (%)",
        title="SLO attainment vs arrival rate\nHigher is better; this is the QLM-style headline metric",
        filename="01_slo_attainment_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="goodput_jobs_per_s",
        y_scale=60.0,
        y_label="Goodput (SLO-met jobs/min)",
        title="Goodput vs arrival rate\nThroughput counted only when jobs meet SLO",
        filename="02_goodput_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="throughput_jobs_per_s",
        y_scale=60.0,
        y_label="Throughput (jobs/min)",
        title="Raw throughput vs arrival rate\nCompare with goodput to expose late completions",
        filename="03_throughput_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="p95_jct_s",
        y_scale=1.0 / 60.0,
        y_label="p95 JCT (min)",
        title="p95 job completion time vs arrival rate\nTail latency is the scheduling stress signal",
        filename="04_p95_jct_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="mean_queue_wait_s",
        y_scale=1.0 / 60.0,
        y_label="Mean queue wait (min)",
        title="Mean queue wait vs arrival rate\nQueue delay reveals saturation before JCT explodes",
        filename="05_queue_wait_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="avg_queue_jobs",
        y_scale=1.0,
        y_label="Avg waiting jobs",
        title="Queue length vs arrival rate\nTime-weighted average number of jobs waiting",
        filename="06_queue_jobs_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="avg_queue_resource_groups",
        y_scale=1.0,
        y_label="Avg queued resource groups",
        title="Resource-group queue length vs arrival rate\nCounts RGs represented in waiting jobs",
        filename="07_rg_queue_length_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="mean_rg_size_turns",
        y_scale=1.0,
        y_label="Mean RG size (turns/RG)",
        title="Resource-group size vs arrival rate\nWorkload mix should be stable; drift means sampling skew",
        filename="08_rg_size_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="mean_prompt_tokens_per_job",
        y_scale=1.0 / 1000.0,
        y_label="Mean prompt tokens/job (K)",
        title="Prompt token usage vs arrival rate\nUseful sanity check for workload mix",
        filename="09_prompt_tokens_vs_arrival_rate.png",
        out_dir=out_dir,
    )
    line_plot(
        rows,
        x_col="arrival_rate_jobs_per_min",
        y_col="cache_hit_rate_turns",
        y_scale=100.0,
        y_label="Turn-level cache hit rate (%)",
        title="Cache hit rate vs arrival rate\nShould stay stable unless policy changes job mix",
        filename="10_cache_hit_rate_vs_arrival_rate.png",
        out_dir=out_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    rows = load_rows(args.input)
    plot_all(rows, args.output_dir)
    print(f"\nWrote plots to {args.output_dir}")


if __name__ == "__main__":
    main()
