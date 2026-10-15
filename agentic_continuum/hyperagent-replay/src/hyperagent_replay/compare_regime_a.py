"""Cross-cell comparator for Regime A replay outputs.

Inputs are 2-4 directories (typically A_stock_baseline, B_stock_reuse,
C_continuum_baseline, D_continuum_reuse) each containing per-trace
`*.replay.json` files produced by `ha-trace-batch-replay` or
`ha-trace-replay-reuse`. Traces are paired across cells by the filename
stem (strips `.baseline.replay.json` / `.reuse.replay.json` /
`.replay.json`).

Emits:

1. `per_trace.csv` — one row per (cell, trace) with wall JCT, LM JCT
   (= GPU-seconds-per-job), per-turn p50/p95/p99 latency, total prompt /
   cached / new-prefill / completion tokens, prefill reuse ratio,
   context retries, and work-avoided ratios vs. a chosen baseline cell.
2. `aggregate.csv` — per-cell means and geomeans across the overlap of
   traces present in every cell (so speedups aren't skewed by missing
   traces).
3. `stage_p95.csv` — per (cell, agent, tool_signature) p50/p95/p99 of
   the actually-measured `request_latency_s` from each replay JSON's
   `turn_metrics`. This is the apples-to-apples "where does the
   speedup land" table.
4. (Optional) `continuum_scheduler_events.csv` — if the Continuum server
   wrote a `scheduler_timestamps` file (via `RUN_OUTPUT_DIR`), pass it
   via `--continuum-scheduler-file` and we extract per-job pin events,
   total pinned duration, eviction events, and queue-wait p95.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from hyperagent_replay.replay import percentile

REPLAY_SUFFIXES = (
    ".baseline.replay.json",
    ".reuse.replay.json",
    ".replay.json",
)


def trace_key_for(path: Path) -> str:
    name = path.name
    for suffix in REPLAY_SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return path.stem


def discover_replays(cell_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(cell_dir.glob("*.replay.json")):
        if path.name.endswith("scheduler_timestamps.json"):
            continue
        key = trace_key_for(path)
        # Prefer the most specific suffix (baseline/reuse > generic).
        found[key] = path
    return found


def safe_get(d: dict[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def work_avoided(baseline: float | None, variant: float | None) -> float | None:
    if baseline is None or variant is None or baseline <= 0:
        return None
    return (baseline - variant) / baseline


def geomean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and v > 0]
    if not clean:
        return None
    log_sum = sum(math.log(v) for v in clean)
    return math.exp(log_sum / len(clean))


def mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def collect_per_turn_latencies(replay: dict[str, Any]) -> list[float]:
    latencies: list[float] = []
    for turn in replay.get("turn_metrics", []) or []:
        v = turn.get("request_latency_s")
        if v is None:
            continue
        # Skip pure cache-hit turns in reuse replays — they didn't hit
        # the LM, so their 0.0 latency would bias stage-level stats.
        if turn.get("cache_hit"):
            continue
        try:
            latencies.append(float(v))
        except (TypeError, ValueError):
            continue
    return latencies


def collect_stage_latencies(
    replay: dict[str, Any],
) -> dict[tuple[str, str], list[float]]:
    stages: dict[tuple[str, str], list[float]] = defaultdict(list)
    for turn in replay.get("turn_metrics", []) or []:
        if turn.get("cache_hit"):
            continue
        latency = turn.get("request_latency_s")
        if latency is None:
            continue
        agent = str(turn.get("agent") or "")
        tool_sig = safe_get(turn, "resource_group", "tool_signature") or "LLM_ONLY"
        stages[(agent, tool_sig)].append(float(latency))
    return stages


def extract_row(cell: str, trace_key: str, replay: dict[str, Any]) -> dict[str, Any]:
    timing = replay.get("timing", {}) or {}
    wall = timing.get("wall_solve_time_s")
    lm = timing.get("lm_only_solve_time_s")
    gpu_s = timing.get("gpu_seconds_per_job")
    if gpu_s is None:
        # Backward-compat for older replays written before the alias landed.
        gpu_s = lm
    prompt_tokens = timing.get("total_prompt_tokens") or 0
    cached = timing.get("total_cached_prompt_tokens") or 0
    new_prefill = timing.get("total_new_prefill_tokens")
    if new_prefill is None:
        new_prefill = max(0, prompt_tokens - cached)
    completion = timing.get("total_completion_tokens") or 0
    reuse_ratio = timing.get("prefill_reuse_ratio") or ratio(cached, prompt_tokens) or 0.0

    executed_latencies = collect_per_turn_latencies(replay)
    p50 = percentile(executed_latencies, 50) if executed_latencies else None
    p95 = percentile(executed_latencies, 95) if executed_latencies else None
    p99 = percentile(executed_latencies, 99) if executed_latencies else None

    num_turns = timing.get("num_replayed_turns", 0)
    num_cache_hits = timing.get("num_cache_hits", 0)
    num_executed = timing.get("num_vllm_requests_executed", num_turns - num_cache_hits)

    return {
        "cell": cell,
        "trace": trace_key,
        "wall_s": wall,
        "lm_s": lm,
        "gpu_seconds_per_job": gpu_s,
        "p50_req_latency_s": p50,
        "p95_req_latency_s": p95,
        "p99_req_latency_s": p99,
        "num_turns": num_turns,
        "num_cache_hits": num_cache_hits,
        "num_executed_vllm": num_executed,
        "total_prompt_tokens": prompt_tokens,
        "total_cached_prompt_tokens": cached,
        "total_new_prefill_tokens": new_prefill,
        "total_completion_tokens": completion,
        "prefill_reuse_ratio": reuse_ratio,
        "num_turns_context_trimmed":
        timing.get("num_turns_context_trimmed", 0),
        "num_context_retry_events":
        timing.get("num_context_retry_events", 0),
        "engine_mode": safe_get(replay, "settings", "engine_mode") or "unknown",
        "reuse_mode": safe_get(replay, "settings", "reuse_mode") or "none",
    }


def load_scheduler_events(path: Path) -> dict[str, dict[str, Any]]:
    """Parse the Continuum server's scheduler_timestamps file.

    Returns a dict keyed by job_id with aggregated metrics:
    num_requests, num_pinned, total_pinned_duration_s, num_evicted,
    num_waiting_to_running, queue_wait_p95_s.
    """
    raw = json.loads(path.read_text())
    result: dict[str, dict[str, Any]] = {}
    for job_id, history in raw.items():
        arrivals: list[float] = []
        waiting_to_running: list[float] = []
        evictions = 0
        pin_pairs: list[tuple[float, float]] = []
        current_pin_start: float | None = None
        num_requests = 0
        # Scheduler_timestamps entries are dicts with a single well-known key.
        # We pair pinned_time -> unpinned_time in order.
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if "Request_arrival_time" in entry:
                arrivals.append(float(entry["Request_arrival_time"]))
                num_requests += 1
            elif "waiting_to_running" in entry:
                waiting_to_running.append(float(entry["waiting_to_running"]))
            elif "Request_evicted_from_running_queue_time" in entry:
                evictions += 1
            elif "pinned_time" in entry:
                current_pin_start = float(entry["pinned_time"])
            elif "unpinned_time" in entry and current_pin_start is not None:
                pin_pairs.append((current_pin_start,
                                  float(entry["unpinned_time"])))
                current_pin_start = None

        # Queue-wait: for each paired (arrival, waiting_to_running) by
        # positional order.
        queue_waits: list[float] = []
        for arrival, wtr in zip(arrivals, waiting_to_running):
            if wtr >= arrival:
                queue_waits.append(wtr - arrival)

        pinned_durations = [end - start for start, end in pin_pairs if end > start]

        result[job_id] = {
            "num_requests": num_requests,
            "num_pinned": len(pin_pairs),
            "total_pinned_duration_s": sum(pinned_durations),
            "avg_pinned_duration_s":
            (sum(pinned_durations) / len(pinned_durations)
             if pinned_durations else 0.0),
            "num_evicted": evictions,
            "num_waiting_to_running": len(waiting_to_running),
            "queue_wait_p50_s":
            percentile(queue_waits, 50) if queue_waits else 0.0,
            "queue_wait_p95_s":
            percentile(queue_waits, 95) if queue_waits else 0.0,
        }
    return result


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def format_row(row: dict[str, Any], fields: list[str]) -> list[str]:
    out: list[str] = []
    for f in fields:
        v = row.get(f)
        if v is None:
            out.append("N/A")
        elif isinstance(v, float):
            out.append(f"{v:.3f}")
        else:
            out.append(str(v))
    return out


def print_table(rows: list[dict[str, Any]], fields: list[str]) -> None:
    if not rows:
        print("(no rows)")
        return
    col_widths = [len(f) for f in fields]
    formatted_rows = [format_row(r, fields) for r in rows]
    for r in formatted_rows:
        for i, cell in enumerate(r):
            col_widths[i] = max(col_widths[i], len(cell))
    fmt = " | ".join("{:" + str(w) + "}" for w in col_widths)
    sep = "-+-".join("-" * w for w in col_widths)
    print(fmt.format(*fields))
    print(sep)
    for r in formatted_rows:
        print(fmt.format(*r))


def parse_cell_args(values: list[str]) -> list[tuple[str, Path]]:
    cells: list[tuple[str, Path]] = []
    for entry in values:
        if "=" not in entry:
            raise SystemExit(
                f"--cell expects NAME=PATH (got {entry!r})")
        name, _, path = entry.partition("=")
        cells.append((name.strip(), Path(path).resolve()))
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regime A cross-cell comparator (JCT / GPU-s / "
        "prefill / work-avoided / stage p95 / Continuum events)")
    parser.add_argument(
        "--cell",
        action="append",
        required=True,
        help=(
            "NAME=DIR entry for a replay-output directory. Repeat for "
            "each cell. Example: --cell A=results/regime_a/A_stock_baseline "
            "--cell C=results/regime_a/C_continuum_baseline"
        ),
    )
    parser.add_argument(
        "--baseline-cell",
        required=True,
        help="Name of the cell to use as the reference for work-avoided "
        "ratios (e.g. A).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for per_trace.csv / aggregate.csv / stage_p95.csv.",
    )
    parser.add_argument(
        "--continuum-scheduler-file",
        type=Path,
        default=None,
        help=(
            "Optional: path to the Continuum server-side "
            "`scheduler_timestamps` file (written by vllm-continuum via "
            "RUN_OUTPUT_DIR). Adds pin / eviction / queue-wait metrics."
        ),
    )
    args = parser.parse_args()

    cells = parse_cell_args(args.cell)
    cell_names = [c[0] for c in cells]
    if args.baseline_cell not in cell_names:
        raise SystemExit(
            f"--baseline-cell {args.baseline_cell!r} must be one of "
            f"{cell_names!r}")

    replays_by_cell: dict[str, dict[str, dict[str, Any]]] = {}
    for name, cell_dir in cells:
        if not cell_dir.is_dir():
            raise SystemExit(f"Cell {name} directory not found: {cell_dir}")
        cell_replays: dict[str, dict[str, Any]] = {}
        for trace_key, path in discover_replays(cell_dir).items():
            try:
                cell_replays[trace_key] = json.loads(path.read_text())
            except Exception as exc:
                print(f"[warn] could not read {path}: {exc}")
        replays_by_cell[name] = cell_replays

    common_keys = set.intersection(
        *(set(r.keys()) for r in replays_by_cell.values())) if replays_by_cell else set()
    all_keys = set()
    for r in replays_by_cell.values():
        all_keys.update(r.keys())
    unique_keys = all_keys - common_keys
    if unique_keys:
        print(f"[info] {len(unique_keys)} trace(s) missing from at least "
              f"one cell, excluded from aggregate: "
              f"{sorted(unique_keys)[:5]}{'…' if len(unique_keys) > 5 else ''}")

    per_trace_rows: list[dict[str, Any]] = []
    for cell_name in cell_names:
        for trace_key, replay in replays_by_cell[cell_name].items():
            per_trace_rows.append(extract_row(cell_name, trace_key, replay))

    # Add work-avoided ratios vs. baseline cell for matching traces.
    baseline_by_trace = {
        r["trace"]: r
        for r in per_trace_rows
        if r["cell"] == args.baseline_cell
    }
    for row in per_trace_rows:
        base = baseline_by_trace.get(row["trace"])
        if base is None or row["cell"] == args.baseline_cell:
            row["work_avoided_prefill_vs_baseline"] = None
            row["work_avoided_gpu_seconds_vs_baseline"] = None
            row["work_avoided_wall_vs_baseline"] = None
            continue
        row["work_avoided_prefill_vs_baseline"] = work_avoided(
            base["total_new_prefill_tokens"],
            row["total_new_prefill_tokens"],
        )
        row["work_avoided_gpu_seconds_vs_baseline"] = work_avoided(
            base["gpu_seconds_per_job"],
            row["gpu_seconds_per_job"],
        )
        row["work_avoided_wall_vs_baseline"] = work_avoided(
            base["wall_s"], row["wall_s"])

    per_trace_fields = [
        "cell", "trace", "engine_mode", "reuse_mode",
        "wall_s", "lm_s", "gpu_seconds_per_job",
        "p50_req_latency_s", "p95_req_latency_s", "p99_req_latency_s",
        "num_turns", "num_cache_hits", "num_executed_vllm",
        "total_prompt_tokens", "total_cached_prompt_tokens",
        "total_new_prefill_tokens", "total_completion_tokens",
        "prefill_reuse_ratio",
        "num_turns_context_trimmed", "num_context_retry_events",
        "work_avoided_prefill_vs_baseline",
        "work_avoided_gpu_seconds_vs_baseline",
        "work_avoided_wall_vs_baseline",
    ]

    # Aggregate only over the intersection of traces present in every cell.
    aggregate_rows: list[dict[str, Any]] = []
    for cell_name in cell_names:
        rows = [
            r for r in per_trace_rows
            if r["cell"] == cell_name and r["trace"] in common_keys
        ]
        if not rows:
            continue
        agg = {
            "cell": cell_name,
            "num_traces": len(rows),
            "mean_wall_s": mean([r["wall_s"] for r in rows]),
            "mean_gpu_seconds_per_job":
            mean([r["gpu_seconds_per_job"] for r in rows]),
            "mean_p95_req_latency_s":
            mean([r["p95_req_latency_s"] for r in rows]),
            "mean_new_prefill_tokens":
            mean([r["total_new_prefill_tokens"] for r in rows]),
            "mean_prefill_reuse_ratio":
            mean([r["prefill_reuse_ratio"] for r in rows]),
            "mean_completion_tokens":
            mean([r["total_completion_tokens"] for r in rows]),
            "geomean_wall_speedup_vs_baseline": None,
            "geomean_gpu_seconds_speedup_vs_baseline": None,
            "geomean_prefill_speedup_vs_baseline": None,
        }
        if cell_name != args.baseline_cell:
            base_rows = {
                r["trace"]: r
                for r in per_trace_rows
                if r["cell"] == args.baseline_cell and r["trace"] in common_keys
            }
            wall_ratios: list[float] = []
            gpu_ratios: list[float] = []
            prefill_ratios: list[float] = []
            for r in rows:
                base = base_rows.get(r["trace"])
                if base is None:
                    continue
                br = ratio(base["wall_s"], r["wall_s"])
                if br is not None and br > 0:
                    wall_ratios.append(br)
                gr = ratio(base["gpu_seconds_per_job"],
                           r["gpu_seconds_per_job"])
                if gr is not None and gr > 0:
                    gpu_ratios.append(gr)
                pr = ratio(base["total_new_prefill_tokens"],
                           r["total_new_prefill_tokens"])
                if pr is not None and pr > 0:
                    prefill_ratios.append(pr)
            agg["geomean_wall_speedup_vs_baseline"] = geomean(wall_ratios)
            agg["geomean_gpu_seconds_speedup_vs_baseline"] = geomean(gpu_ratios)
            agg["geomean_prefill_speedup_vs_baseline"] = geomean(prefill_ratios)
        aggregate_rows.append(agg)

    aggregate_fields = [
        "cell", "num_traces",
        "mean_wall_s", "mean_gpu_seconds_per_job", "mean_p95_req_latency_s",
        "mean_new_prefill_tokens", "mean_prefill_reuse_ratio",
        "mean_completion_tokens",
        "geomean_wall_speedup_vs_baseline",
        "geomean_gpu_seconds_speedup_vs_baseline",
        "geomean_prefill_speedup_vs_baseline",
    ]

    # Stage-level latencies (agent × tool_signature) per cell.
    stage_rows: list[dict[str, Any]] = []
    for cell_name in cell_names:
        bucket: dict[tuple[str, str], list[float]] = defaultdict(list)
        for trace_key, replay in replays_by_cell[cell_name].items():
            for key, latencies in collect_stage_latencies(replay).items():
                bucket[key].extend(latencies)
        for (agent, tool_sig), latencies in sorted(bucket.items()):
            stage_rows.append({
                "cell": cell_name,
                "agent": agent,
                "tool_signature": tool_sig,
                "n": len(latencies),
                "p50_s": percentile(latencies, 50) if latencies else None,
                "p95_s": percentile(latencies, 95) if latencies else None,
                "p99_s": percentile(latencies, 99) if latencies else None,
                "total_s": sum(latencies),
            })
    stage_fields = [
        "cell", "agent", "tool_signature", "n",
        "p50_s", "p95_s", "p99_s", "total_s",
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "per_trace.csv", per_trace_rows, per_trace_fields)
    write_csv(args.output_dir / "aggregate.csv", aggregate_rows, aggregate_fields)
    write_csv(args.output_dir / "stage_p95.csv", stage_rows, stage_fields)

    print("=== per-cell aggregate (over traces present in every cell) ===")
    print_table(aggregate_rows, aggregate_fields)

    if args.continuum_scheduler_file:
        if not args.continuum_scheduler_file.is_file():
            raise SystemExit(
                f"--continuum-scheduler-file not found: "
                f"{args.continuum_scheduler_file}")
        events = load_scheduler_events(args.continuum_scheduler_file)
        event_rows = [
            {"job_id": job_id, **metrics}
            for job_id, metrics in sorted(events.items())
        ]
        event_fields = [
            "job_id", "num_requests", "num_pinned",
            "total_pinned_duration_s", "avg_pinned_duration_s",
            "num_evicted", "num_waiting_to_running",
            "queue_wait_p50_s", "queue_wait_p95_s",
        ]
        write_csv(args.output_dir / "continuum_scheduler_events.csv",
                  event_rows, event_fields)
        print("\n=== continuum scheduler events (per job_id) ===")
        print_table(event_rows, event_fields)

    print(f"\nWrote CSVs to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
