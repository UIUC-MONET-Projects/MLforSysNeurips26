#!/usr/bin/env python3
"""
Regenerate Phase 1 ShareGPT figures using pretty-plots styling (same data as phase1_sharegpt.ipynb).

Run from repo root:
  python conversational_qlm/generate_phase1_pretty_plots.py

Or from conversational_qlm/:
  python generate_phase1_pretty_plots.py

Requires a checkout of https://github.com/raginigupta6/pretty-plots at <repo root>/pretty-plots
(packaging note: docstring paths updated from analysis/ to conversational_qlm/).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# pretty-plots: publication-style matplotlib defaults (Times New Roman, seaborn palette, etc.)
# Import `utils` before pyplot so matplotlib backend/rcParams are set correctly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "pretty-plots"))
import utils  # noqa: E402, F401
from utils import COLOR, LINESTYLE, MARKER, matplotlib, plt  # noqa: E402

# packaging: results now live next to this script (was _REPO_ROOT / "results" / "phase1")
RESULTS_DIR = Path(__file__).resolve().parent / "results" / "phase1"
PLOTS_DIR = Path(__file__).resolve().parent / "plots_pretty"


def load_metrics(filename: str):
    path = RESULTS_DIR / filename
    if not path.exists():
        print(f"Warning: {filename} not found")
        return None
    with open(path) as f:
        return json.load(f)


def load_experiments():
    experiments = {
        "E1.1": {"name": "vLLM Baseline", "file": "vllm_baseline_mixed.json", "system": "vLLM"},
        "E1.2": {"name": "QLM Baseline", "file": "qlm_baseline_mixed.json", "system": "QLM"},
        "E1.3": {"name": "vLLM High Rate", "file": "vllm_high_rate.json", "system": "vLLM"},
        "E1.4": {"name": "QLM High Rate", "file": "qlm_high_rate.json", "system": "QLM"},
        "E1.5": {"name": "vLLM Bursty", "file": "vllm_bursty.json", "system": "vLLM"},
        "E1.6": {"name": "QLM Bursty", "file": "qlm_bursty.json", "system": "QLM"},
        "E1.7": {"name": "vLLM Multi-User", "file": "vllm_multiuser.json", "system": "vLLM"},
        "E1.8": {"name": "QLM Multi-User", "file": "qlm_multiuser.json", "system": "QLM"},
        "E1.9": {"name": "vLLM Short", "file": "vllm_short_prompts.json", "system": "vLLM"},
        "E1.10": {"name": "QLM Short", "file": "qlm_short_prompts.json", "system": "QLM"},
        "E1.11": {"name": "vLLM Long", "file": "vllm_long_prompts.json", "system": "vLLM"},
        "E1.12": {"name": "QLM Long", "file": "qlm_long_prompts.json", "system": "QLM"},
    }
    for exp in experiments.values():
        exp["data"] = load_metrics(exp["file"])
    return experiments


def save_figure(fig, stem: str) -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    base = PLOTS_DIR / stem
    for ext in ("png", "pdf"):
        out = f"{base}.{ext}"
        if ext == "png":
            fig.savefig(out, bbox_inches="tight", dpi=150)
        else:
            fig.savefig(out, bbox_inches="tight")
        print(f"Saved {out}")
    plt.close(fig)


def _boxplot_single(ax, data, position: int, color: str, width: float = 0.55) -> None:
    lw = 2
    bg = matplotlib.colors.to_rgba(color, alpha=0.2)
    ax.boxplot(
        [data],
        positions=[position],
        patch_artist=True,
        showfliers=False,
        widths=width,
        capwidths=0.35,
        tick_labels=[""],
        boxprops=dict(facecolor=bg, edgecolor=color, linewidth=lw),
        whiskerprops=dict(color=color, linewidth=lw),
        capprops=dict(color=color, linewidth=lw),
        medianprops=dict(color=color, linewidth=lw),
    )


def plot1_scheduling_delay_baseline(experiments) -> None:
    vllm_delays = [d["delay_ms"] for d in experiments["E1.1"]["data"]["scheduling_delays"]]
    qlm_delays = [d["delay_ms"] for d in experiments["E1.2"]["data"]["scheduling_delays"]]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    for delays, label, color, ls, mk in [
        (vllm_delays, "vLLM", COLOR[0], LINESTYLE[0], MARKER[0]),
        (qlm_delays, "QLM", COLOR[1], LINESTYLE[1], MARKER[1]),
    ]:
        sorted_delays = np.sort(delays)
        cdf = np.arange(1, len(sorted_delays) + 1) / len(sorted_delays)
        ax.plot(
            sorted_delays,
            cdf,
            label=label,
            color=color,
            linestyle=ls,
            marker=mk,
            markevery=max(1, len(sorted_delays) // 20),
            clip_on=False,
        )
    ax.set_xlabel("Scheduling delay (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("Scheduling delay CDF (baseline: 2 rps, mixed prompts)")
    ax.legend(loc="lower right")
    ax.yaxis.grid(True, alpha=0.35)

    ax = axes[1]
    _boxplot_single(ax, vllm_delays, 0, COLOR[0])
    _boxplot_single(ax, qlm_delays, 1, COLOR[1])
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["vLLM", "QLM"])
    ax.set_ylabel("Scheduling delay (ms)")
    ax.set_title("Scheduling delay distribution")
    ax.yaxis.grid(True, alpha=0.35)

    plt.tight_layout()
    save_figure(fig, "plot1_scheduling_delay_baseline")


def plot2_queue_length_over_time(experiments) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    comparisons = [
        ("E1.1", "E1.2", "Baseline (2 rps)", axes[0, 0]),
        ("E1.3", "E1.4", "High rate (5 rps)", axes[0, 1]),
        ("E1.5", "E1.6", "Bursty traffic", axes[1, 0]),
        ("E1.7", "E1.8", "Multi-user (8 users)", axes[1, 1]),
    ]

    for vllm_exp, qlm_exp, title, ax in comparisons:
        vllm_data = experiments[vllm_exp]["data"]
        qlm_data = experiments[qlm_exp]["data"]
        if vllm_data is None or qlm_data is None:
            continue
        vllm_queue = vllm_data["queue_length_samples"]
        qlm_queue = qlm_data["queue_length_samples"]
        vllm_t0 = vllm_queue[0]["t"] if vllm_queue else 0
        qlm_t0 = qlm_queue[0]["t"] if qlm_queue else 0
        vllm_times = [s["t"] - vllm_t0 for s in vllm_queue]
        vllm_lengths = [s["length"] for s in vllm_queue]
        qlm_times = [s["t"] - qlm_t0 for s in qlm_queue]
        qlm_lengths = [s["length"] for s in qlm_queue]

        ax.plot(
            vllm_times,
            vllm_lengths,
            label="vLLM",
            color=COLOR[0],
            linestyle=LINESTYLE[0],
            linewidth=2,
            alpha=0.9,
            clip_on=False,
        )
        ax.plot(
            qlm_times,
            qlm_lengths,
            label="QLM",
            color=COLOR[1],
            linestyle=LINESTYLE[1],
            linewidth=2,
            alpha=0.9,
            clip_on=False,
        )
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Queue length")
        ax.set_title(title)
        ax.legend(loc="upper right")
        ax.yaxis.grid(True, alpha=0.35)

    plt.tight_layout()
    save_figure(fig, "plot2_queue_length_over_time")


def plot3_throughput_vs_load(experiments) -> None:
    load_experiments = [
        ("E1.1", "E1.2", "2 rps"),
        ("E1.3", "E1.4", "5 rps"),
    ]
    vllm_throughputs = []
    qlm_throughputs = []
    load_labels = []
    for vllm_exp, qlm_exp, label in load_experiments:
        vllm_data = experiments[vllm_exp]["data"]
        qlm_data = experiments[qlm_exp]["data"]
        if vllm_data is None or qlm_data is None:
            continue
        vllm_duration = vllm_data.get("duration_sec", 60)
        qlm_duration = qlm_data.get("duration_sec", 60)
        vllm_throughputs.append(vllm_data["summary"]["num_requests_dispatched"] / vllm_duration)
        qlm_throughputs.append(qlm_data["summary"]["num_requests_dispatched"] / qlm_duration)
        load_labels.append(label)

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(load_labels))
    width = 0.36
    ax.bar(
        x - width / 2,
        vllm_throughputs,
        width,
        label="vLLM",
        color=COLOR[0],
        edgecolor=COLOR[0],
        linewidth=1.2,
    )
    ax.bar(
        x + width / 2,
        qlm_throughputs,
        width,
        label="QLM",
        color=COLOR[1],
        edgecolor=COLOR[1],
        linewidth=1.2,
    )
    ax.set_xlabel("Arrival rate")
    ax.set_ylabel("Throughput (requests/s)")
    ax.set_title("Throughput vs load (ShareGPT baseline)")
    ax.set_xticks(x)
    ax.set_xticklabels(load_labels)
    ax.legend()
    ax.yaxis.grid(True, alpha=0.35)

    plt.tight_layout()
    save_figure(fig, "plot3_throughput_vs_load")


def plot4_prompt_length_sensitivity(experiments) -> None:
    prompt_experiments = [
        ("E1.9", "E1.10", "Short ($\\leq$200 chars)"),
        ("E1.1", "E1.2", "Mixed"),
        ("E1.11", "E1.12", "Long ($>$1000 chars)"),
    ]
    metrics_to_plot = [
        ("scheduling_delay_ms_mean", "Mean scheduling delay (ms)"),
        ("scheduling_delay_ms_p99", "P99 scheduling delay (ms)"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for idx, (metric_key, metric_label) in enumerate(metrics_to_plot):
        ax = axes[idx]
        vllm_values = []
        qlm_values = []
        prompt_labels = []
        for vllm_exp, qlm_exp, label in prompt_experiments:
            vllm_data = experiments[vllm_exp]["data"]
            qlm_data = experiments[qlm_exp]["data"]
            if vllm_data is None or qlm_data is None:
                continue
            vllm_values.append(vllm_data["summary"].get(metric_key, 0))
            qlm_values.append(qlm_data["summary"].get(metric_key, 0))
            prompt_labels.append(label)

        x = np.arange(len(prompt_labels))
        width = 0.36
        ax.bar(x - width / 2, vllm_values, width, label="vLLM", color=COLOR[0], edgecolor=COLOR[0], linewidth=1.2)
        ax.bar(x + width / 2, qlm_values, width, label="QLM", color=COLOR[1], edgecolor=COLOR[1], linewidth=1.2)
        ax.set_xlabel("Prompt length category")
        ax.set_ylabel(metric_label)
        ax.set_title(f"{metric_label} by prompt length")
        ax.set_xticks(x)
        ax.set_xticklabels(prompt_labels, rotation=18, ha="right")
        ax.legend()
        ax.yaxis.grid(True, alpha=0.35)

    plt.tight_layout()
    save_figure(fig, "plot4_prompt_length_sensitivity")


def plot5_queue_dynamics_summary(experiments) -> None:
    exp_names = []
    vllm_mean_queue = []
    qlm_mean_queue = []
    vllm_max_queue = []
    qlm_max_queue = []
    pairs = [
        ("E1.1", "E1.2", "Baseline"),
        ("E1.3", "E1.4", "High rate"),
        ("E1.5", "E1.6", "Bursty"),
        ("E1.7", "E1.8", "Multi-user"),
    ]
    for vllm_exp, qlm_exp, label in pairs:
        vllm_data = experiments[vllm_exp]["data"]
        qlm_data = experiments[qlm_exp]["data"]
        if vllm_data is None or qlm_data is None:
            continue
        exp_names.append(label)
        vllm_mean_queue.append(vllm_data["summary"].get("queue_length_mean", 0))
        qlm_mean_queue.append(qlm_data["summary"].get("queue_length_mean", 0))
        vllm_max_queue.append(vllm_data["summary"].get("queue_length_max", 0))
        qlm_max_queue.append(qlm_data["summary"].get("queue_length_max", 0))

    x = np.arange(len(exp_names))
    width = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    ax.bar(x - width / 2, vllm_mean_queue, width, label="vLLM", color=COLOR[0], edgecolor=COLOR[0], linewidth=1.2)
    ax.bar(x + width / 2, qlm_mean_queue, width, label="QLM", color=COLOR[1], edgecolor=COLOR[1], linewidth=1.2)
    ax.set_xlabel("Experiment")
    ax.set_ylabel("Mean queue length")
    ax.set_title("Mean queue length comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_names, rotation=18, ha="right")
    ax.legend()
    ax.yaxis.grid(True, alpha=0.35)

    ax = axes[1]
    ax.bar(x - width / 2, vllm_max_queue, width, label="vLLM", color=COLOR[0], edgecolor=COLOR[0], linewidth=1.2)
    ax.bar(x + width / 2, qlm_max_queue, width, label="QLM", color=COLOR[1], edgecolor=COLOR[1], linewidth=1.2)
    ax.set_xlabel("Experiment")
    ax.set_ylabel("Max queue length")
    ax.set_title("Max queue length comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_names, rotation=18, ha="right")
    ax.legend()
    ax.yaxis.grid(True, alpha=0.35)

    plt.tight_layout()
    save_figure(fig, "plot5_queue_dynamics_summary")


def main() -> None:
    experiments = load_experiments()
    loaded = [eid for eid, exp in experiments.items() if exp["data"] is not None]
    print(f"Loaded {len(loaded)}/{len(experiments)} experiments: {loaded}")
    if len(loaded) < 12:
        print("Warning: some experiment JSON files are missing; plots may fail.")

    plot1_scheduling_delay_baseline(experiments)
    plot2_queue_length_over_time(experiments)
    plot3_throughput_vs_load(experiments)
    plot4_prompt_length_sensitivity(experiments)
    plot5_queue_dynamics_summary(experiments)
    print(f"\nAll pretty-style figures written under: {PLOTS_DIR.resolve()}")


if __name__ == "__main__":
    main()
