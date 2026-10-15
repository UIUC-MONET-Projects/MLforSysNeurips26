#!/usr/bin/env python3
"""
Arrival-rate sweep simulator for Continuum + SLO queueing.

This is intentionally lightweight and deterministic. It does not need a live
vLLM server. It uses the measured/simulated HyperAgent trace metrics already in
results/data/ to build a multi-job queueing workload.

Outputs:
  continuum_slo_framework/outputs/slo_sweep.csv
  continuum_slo_framework/outputs/job_level.csv
"""

from __future__ import annotations

import argparse
import csv
import heapq
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
# packaging: results/data moved to agentic_continuum/results/data (ROOT is supplementary/)
DEFAULT_INSTANCE_SUMMARY = os.path.join(ROOT, "..", "agentic_continuum", "results", "data", "instance_summary.csv")
DEFAULT_TURN_TRACE = os.path.join(ROOT, "..", "agentic_continuum", "results", "data", "full_trace_per_turn.csv")
DEFAULT_SLO_CONFIG = os.path.join(HERE, "configs", "slo_budgets.json")
DEFAULT_OUTPUT_DIR = os.path.join(HERE, "outputs")


@dataclass(frozen=True)
class JobTemplate:
    instance_id: str
    condition: str
    job_size_class: str
    service_time_s: float
    prompt_tokens: float
    completion_tokens: float
    cache_hit_pct: float
    n_turns: int
    n_cache_hits: int
    rg_count: int
    mean_rg_size: float
    max_rg_size: int


@dataclass
class SimJob:
    job_id: int
    template: JobTemplate
    arrival_time_s: float
    slo_budget_s: float
    start_time_s: float | None = None
    finish_time_s: float | None = None
    queue_wait_s: float | None = None

    @property
    def deadline_s(self) -> float:
        return self.arrival_time_s + self.slo_budget_s

    @property
    def jct_s(self) -> float:
        if self.finish_time_s is None:
            return math.nan
        return self.finish_time_s - self.arrival_time_s

    @property
    def slo_met(self) -> bool:
        return self.jct_s <= self.slo_budget_s


@dataclass
class SimResult:
    backend: str
    policy: str
    arrival_rate: float
    jobs: list[SimJob]
    avg_queue_jobs: float
    p95_queue_jobs: float
    avg_queue_resource_groups: float
    p95_queue_resource_groups: float
    total_time_s: float


def load_csv_dicts(path: str) -> list[dict[str, Any]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def inum(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return math.nan
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * pct / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def resource_group_key(row: dict[str, Any]) -> str:
    agent = row.get("agent", "unknown")
    tool = row.get("tool_name", "unknown")
    prompt_bucket = row.get("prompt_bucket", "unknown")
    completion_bucket = row.get("completion_bucket", "unknown")
    return f"{agent}|{tool}|{prompt_bucket}|{completion_bucket}"


def load_resource_group_stats(turn_trace_path: str) -> dict[tuple[str, str], dict[str, float]]:
    rows = load_csv_dicts(turn_trace_path)
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = (str(row["instance_id"]), str(row["condition"]))
        grouped[key][resource_group_key(row)] += 1

    stats: dict[tuple[str, str], dict[str, float]] = {}
    for key, counter in grouped.items():
        sizes = list(counter.values())
        stats[key] = {
            "rg_count": float(len(counter)),
            "mean_rg_size": float(sum(sizes) / max(len(sizes), 1)),
            "max_rg_size": float(max(sizes) if sizes else 0),
        }
    return stats


def load_templates(instance_summary_path: str, turn_trace_path: str) -> dict[str, list[JobTemplate]]:
    rg_stats = load_resource_group_stats(turn_trace_path)
    templates_by_backend: dict[str, list[JobTemplate]] = defaultdict(list)

    for row in load_csv_dicts(instance_summary_path):
        condition = str(row["condition"])
        instance_id = str(row["instance_id"])
        rg = rg_stats.get((instance_id, condition), {})
        template = JobTemplate(
            instance_id=instance_id,
            condition=condition,
            job_size_class=str(row.get("job_size_class", "medium")),
            service_time_s=fnum(row["total_wall_time_s"]),
            prompt_tokens=fnum(row["total_prompt_tokens"]),
            completion_tokens=fnum(row["total_completion_tokens"]),
            cache_hit_pct=fnum(row.get("cache_hit_pct", 0.0)),
            n_turns=inum(row.get("n_turns", 0)),
            n_cache_hits=inum(row.get("n_cache_hits", 0)),
            rg_count=inum(rg.get("rg_count", 1), 1),
            mean_rg_size=fnum(rg.get("mean_rg_size", 1.0), 1.0),
            max_rg_size=inum(rg.get("max_rg_size", 1), 1),
        )
        templates_by_backend[condition].append(template)

    return dict(templates_by_backend)


def load_slo_budgets(path: str) -> dict[str, float]:
    with open(path) as f:
        data = json.load(f)
    return {k: float(v) for k, v in data["job_slo_seconds"].items()}


def parse_list(value: str, cast: Any) -> list[Any]:
    return [cast(v.strip()) for v in value.split(",") if v.strip()]


def job_priority(job: SimJob, policy: str, now: float, sequence_id: int) -> tuple[float, int]:
    tmpl = job.template
    if policy == "fcfs":
        return (job.arrival_time_s, sequence_id)

    if policy == "edf":
        return (job.deadline_s, sequence_id)

    if policy == "cache_aware_edf":
        # Lower score wins. Cache-heavy jobs get pulled slightly earlier because
        # Continuum can amortize pinned KV blocks across their future turns.
        cache_bonus_s = tmpl.cache_hit_pct * 2.0
        return (job.deadline_s - cache_bonus_s, sequence_id)

    if policy == "slack_cache":
        # Slack = time remaining until deadline after estimated service.
        # Smaller slack is more urgent. Add cache/RG bonuses, and aging is
        # implicit because slack decreases with current time.
        slack_s = job.deadline_s - now - tmpl.service_time_s
        cache_bonus_s = tmpl.cache_hit_pct * 2.0
        rg_bonus_s = min(30.0, tmpl.rg_count * 1.5)
        return (slack_s - cache_bonus_s - rg_bonus_s, sequence_id)

    raise ValueError(f"Unknown policy: {policy}")


def generate_arrivals(
    *,
    templates: list[JobTemplate],
    arrival_rate: float,
    n_jobs: int,
    rng: random.Random,
) -> list[SimJob]:
    t = 0.0
    jobs: list[SimJob] = []
    for i in range(n_jobs):
        if i == 0:
            t = 0.0
        else:
            t += rng.expovariate(arrival_rate)
        tmpl = rng.choice(templates)
        jobs.append(SimJob(job_id=i, template=tmpl, arrival_time_s=t, slo_budget_s=0.0))
    return jobs


def simulate_one(
    *,
    backend: str,
    policy: str,
    templates: list[JobTemplate],
    arrival_rate: float,
    n_jobs: int,
    workers: int,
    slo_budgets: dict[str, float],
    seed: int,
) -> SimResult:
    rng = random.Random(seed)
    jobs = generate_arrivals(
        templates=templates,
        arrival_rate=arrival_rate,
        n_jobs=n_jobs,
        rng=rng,
    )
    for job in jobs:
        job.slo_budget_s = slo_budgets.get(job.template.job_size_class, slo_budgets.get("medium", 900.0))

    arrivals = sorted(jobs, key=lambda j: j.arrival_time_s)
    arrival_idx = 0
    waiting: list[SimJob] = []
    in_service: list[tuple[float, int, SimJob]] = []
    available_workers = workers
    now = 0.0
    last_t = 0.0
    sequence = 0

    queue_job_area = 0.0
    queue_rg_area = 0.0
    queue_job_samples: list[float] = []
    queue_rg_samples: list[float] = []

    def accumulate_until(new_t: float) -> None:
        nonlocal last_t, queue_job_area, queue_rg_area
        if new_t <= last_t:
            return
        dt = new_t - last_t
        q_jobs = len(waiting)
        q_rg = sum(j.template.rg_count for j in waiting)
        queue_job_area += q_jobs * dt
        queue_rg_area += q_rg * dt
        queue_job_samples.append(float(q_jobs))
        queue_rg_samples.append(float(q_rg))
        last_t = new_t

    def schedule_available() -> None:
        nonlocal available_workers, sequence
        while available_workers > 0 and waiting:
            scored = [
                (job_priority(job, policy, now, i), i, job)
                for i, job in enumerate(waiting)
            ]
            _, idx, job = min(scored, key=lambda x: x[0])
            waiting.pop(idx)
            job.start_time_s = now
            job.queue_wait_s = now - job.arrival_time_s
            finish = now + job.template.service_time_s
            job.finish_time_s = finish
            heapq.heappush(in_service, (finish, sequence, job))
            sequence += 1
            available_workers -= 1

    while arrival_idx < len(arrivals) or waiting or in_service:
        schedule_available()

        next_arrival = arrivals[arrival_idx].arrival_time_s if arrival_idx < len(arrivals) else math.inf
        next_completion = in_service[0][0] if in_service else math.inf
        next_t = min(next_arrival, next_completion)
        if math.isinf(next_t):
            break

        accumulate_until(next_t)
        now = next_t

        while in_service and in_service[0][0] <= now + 1e-9:
            heapq.heappop(in_service)
            available_workers += 1

        while arrival_idx < len(arrivals) and arrivals[arrival_idx].arrival_time_s <= now + 1e-9:
            waiting.append(arrivals[arrival_idx])
            arrival_idx += 1

    total_time = max((j.finish_time_s or 0.0) for j in jobs) - min(j.arrival_time_s for j in jobs)
    denom = max(total_time, 1e-9)
    return SimResult(
        backend=backend,
        policy=policy,
        arrival_rate=arrival_rate,
        jobs=jobs,
        avg_queue_jobs=queue_job_area / denom,
        p95_queue_jobs=percentile(queue_job_samples, 95),
        avg_queue_resource_groups=queue_rg_area / denom,
        p95_queue_resource_groups=percentile(queue_rg_samples, 95),
        total_time_s=total_time,
    )


def aggregate_result(result: SimResult) -> dict[str, Any]:
    jobs = result.jobs
    jcts = [j.jct_s for j in jobs]
    waits = [j.queue_wait_s or 0.0 for j in jobs]
    slo_met = [j.slo_met for j in jobs]
    total_prompt = sum(j.template.prompt_tokens for j in jobs)
    total_completion = sum(j.template.completion_tokens for j in jobs)
    total_cache_hits = sum(j.template.n_cache_hits for j in jobs)
    total_turns = sum(j.template.n_turns for j in jobs)
    total_rg = sum(j.template.rg_count for j in jobs)

    return {
        "backend": result.backend,
        "policy": result.policy,
        "arrival_rate_jobs_per_s": result.arrival_rate,
        "arrival_rate_jobs_per_min": result.arrival_rate * 60.0,
        "n_jobs": len(jobs),
        "workers": "",
        "slo_met_rate": sum(slo_met) / max(len(slo_met), 1),
        "slo_violations": len(slo_met) - sum(slo_met),
        "throughput_jobs_per_s": len(jobs) / max(result.total_time_s, 1e-9),
        "goodput_jobs_per_s": sum(slo_met) / max(result.total_time_s, 1e-9),
        "mean_jct_s": sum(jcts) / max(len(jcts), 1),
        "p50_jct_s": percentile(jcts, 50),
        "p95_jct_s": percentile(jcts, 95),
        "p99_jct_s": percentile(jcts, 99),
        "mean_queue_wait_s": sum(waits) / max(len(waits), 1),
        "p95_queue_wait_s": percentile(waits, 95),
        "avg_queue_jobs": result.avg_queue_jobs,
        "p95_queue_jobs": result.p95_queue_jobs,
        "avg_queue_resource_groups": result.avg_queue_resource_groups,
        "p95_queue_resource_groups": result.p95_queue_resource_groups,
        "mean_resource_groups_per_job": total_rg / max(len(jobs), 1),
        "mean_rg_size_turns": sum(j.template.mean_rg_size for j in jobs) / max(len(jobs), 1),
        "mean_max_rg_size_turns": sum(j.template.max_rg_size for j in jobs) / max(len(jobs), 1),
        "mean_prompt_tokens_per_job": total_prompt / max(len(jobs), 1),
        "mean_completion_tokens_per_job": total_completion / max(len(jobs), 1),
        "cache_hit_rate_turns": total_cache_hits / max(total_turns, 1),
        "total_time_s": result.total_time_s,
    }


def job_level_rows(result: SimResult) -> list[dict[str, Any]]:
    rows = []
    for job in result.jobs:
        rows.append(
            {
                "backend": result.backend,
                "policy": result.policy,
                "arrival_rate_jobs_per_s": result.arrival_rate,
                "job_id": job.job_id,
                "instance_id": job.template.instance_id,
                "job_size_class": job.template.job_size_class,
                "arrival_time_s": job.arrival_time_s,
                "start_time_s": job.start_time_s,
                "finish_time_s": job.finish_time_s,
                "queue_wait_s": job.queue_wait_s,
                "jct_s": job.jct_s,
                "slo_budget_s": job.slo_budget_s,
                "slo_met": int(job.slo_met),
                "prompt_tokens": job.template.prompt_tokens,
                "completion_tokens": job.template.completion_tokens,
                "cache_hit_pct": job.template.cache_hit_pct,
                "n_turns": job.template.n_turns,
                "resource_groups": job.template.rg_count,
                "mean_rg_size_turns": job.template.mean_rg_size,
                "max_rg_size_turns": job.template.max_rg_size,
            }
        )
    return rows


def write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def stable_int_seed(text: str) -> int:
    digest = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-summary", default=DEFAULT_INSTANCE_SUMMARY)
    parser.add_argument("--turn-trace", default=DEFAULT_TURN_TRACE)
    parser.add_argument("--slo-config", default=DEFAULT_SLO_CONFIG)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--arrival-rates", default="0.002,0.004,0.006,0.008,0.010,0.012")
    parser.add_argument("--policies", default="fcfs,edf,cache_aware_edf,slack_cache")
    parser.add_argument("--backends", default="stock_vllm,continuum")
    parser.add_argument("--jobs", type=int, default=300)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    templates_by_backend = load_templates(args.instance_summary, args.turn_trace)
    slo_budgets = load_slo_budgets(args.slo_config)
    arrival_rates = parse_list(args.arrival_rates, float)
    policies = parse_list(args.policies, str)
    backends = parse_list(args.backends, str)

    aggregate_rows: list[dict[str, Any]] = []
    all_job_rows: list[dict[str, Any]] = []

    for backend in backends:
        if backend not in templates_by_backend:
            raise SystemExit(f"No templates for backend/condition '{backend}'. Available: {sorted(templates_by_backend)}")
        for policy in policies:
            for rate in arrival_rates:
                result = simulate_one(
                    backend=backend,
                    policy=policy,
                    templates=templates_by_backend[backend],
                    arrival_rate=rate,
                    n_jobs=args.jobs,
                    workers=args.workers,
                    slo_budgets=slo_budgets,
                    # Same backend/rate workload across policies so policy curves
                    # are comparable. Policy changes only the scheduling order.
                    seed=args.seed + int(rate * 1_000_000) + stable_int_seed(backend) % 10_000,
                )
                row = aggregate_result(result)
                row["workers"] = args.workers
                aggregate_rows.append(row)
                all_job_rows.extend(job_level_rows(result))
                print(
                    f"{backend:10s} {policy:15s} lambda={rate:.4f}/s "
                    f"slo={row['slo_met_rate']:.2f} p95_jct={row['p95_jct_s']:.1f}s "
                    f"goodput={row['goodput_jobs_per_s']:.4f}/s"
                )

    sweep_path = os.path.join(args.output_dir, "slo_sweep.csv")
    jobs_path = os.path.join(args.output_dir, "job_level.csv")
    write_csv(sweep_path, aggregate_rows)
    write_csv(jobs_path, all_job_rows)
    print(f"\nWrote {sweep_path}")
    print(f"Wrote {jobs_path}")


if __name__ == "__main__":
    main()
