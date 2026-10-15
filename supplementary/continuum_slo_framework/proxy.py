#!/usr/bin/env python3
"""
OpenAI-compatible SLO queue proxy for Continuum/vLLM.

This proxy accepts /v1/chat/completions, queues requests using an SLO-aware
policy, forwards them to an upstream OpenAI-compatible Continuum server, and
logs queue/service/token metrics.

Example:
  python3.11 continuum_slo_framework/proxy.py \
    --upstream http://127.0.0.1:8000/v1 \
    --port 8010 \
    --policy cache_aware_edf \
    --workers 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse


@dataclass(order=True)
class QueuedRequest:
    priority: float
    sequence: int
    request_id: str = field(compare=False)
    arrival_time: float = field(compare=False)
    body: dict[str, Any] = field(compare=False)
    headers: dict[str, str] = field(compare=False)
    job_id: str = field(compare=False)
    resource_group: str = field(compare=False)
    slo_budget_s: float = field(compare=False)
    cache_score: float = field(compare=False)
    future: asyncio.Future = field(compare=False)


class SloQueueProxy:
    def __init__(
        self,
        *,
        upstream_base_url: str,
        policy: str,
        workers: int,
        metrics_jsonl: str,
        timeout_s: float,
    ) -> None:
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.policy = policy
        self.workers = workers
        self.metrics_jsonl = metrics_jsonl
        self.timeout_s = timeout_s
        self.queue: asyncio.PriorityQueue[QueuedRequest] = asyncio.PriorityQueue()
        self.sequence = 0
        self.started = False
        self.client = httpx.AsyncClient(timeout=timeout_s)
        self.summary = {
            "accepted": 0,
            "completed": 0,
            "failed": 0,
            "slo_met": 0,
            "total_queue_wait_s": 0.0,
            "total_service_s": 0.0,
        }
        os.makedirs(os.path.dirname(metrics_jsonl) or ".", exist_ok=True)

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        for idx in range(self.workers):
            asyncio.create_task(self.worker_loop(idx))

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def compute_priority(
        self,
        *,
        arrival_time: float,
        slo_budget_s: float,
        cache_score: float,
        resource_group: str,
        sequence: int,
    ) -> float:
        deadline = arrival_time + slo_budget_s

        if self.policy == "fcfs":
            return arrival_time
        if self.policy == "edf":
            return deadline
        if self.policy == "cache_aware_edf":
            return deadline - 2.0 * cache_score
        if self.policy == "slack_cache":
            # At enqueue time this is equivalent to SLO budget, but the cache/RG
            # terms make hot resource groups earlier. Aging is provided by FCFS
            # tie-breaking through sequence.
            rg_bonus = 5.0 if resource_group and resource_group != "unknown" else 0.0
            return slo_budget_s - 2.0 * cache_score - rg_bonus
        raise ValueError(f"Unknown policy: {self.policy}")

    async def enqueue(self, body: dict[str, Any], headers: dict[str, str]) -> Any:
        if body.get("stream"):
            raise HTTPException(
                status_code=400,
                detail="SLO proxy currently supports non-streaming chat completions only.",
            )

        arrival = time.time()
        extra = body.get("extra_body") or {}
        job_id = str(extra.get("job_id") or body.get("job_id") or headers.get("x-monet-job-id") or "unknown")
        resource_group = infer_resource_group(body, extra)
        slo_budget_s = float(extra.get("slo_budget_s") or headers.get("x-monet-slo-budget-s") or 900.0)
        cache_score = float(extra.get("cache_score") or estimate_cache_score(body, extra))
        seq = self.next_sequence()
        priority = self.compute_priority(
            arrival_time=arrival,
            slo_budget_s=slo_budget_s,
            cache_score=cache_score,
            resource_group=resource_group,
            sequence=seq,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        qreq = QueuedRequest(
            priority=priority,
            sequence=seq,
            request_id=str(uuid.uuid4()),
            arrival_time=arrival,
            body=body,
            headers=headers,
            job_id=job_id,
            resource_group=resource_group,
            slo_budget_s=slo_budget_s,
            cache_score=cache_score,
            future=future,
        )
        await self.queue.put(qreq)
        self.summary["accepted"] += 1
        return await future

    async def worker_loop(self, worker_id: int) -> None:
        while True:
            qreq = await self.queue.get()
            start = time.time()
            queue_wait_s = start - qreq.arrival_time
            status_code = 500
            response_json: dict[str, Any] | None = None
            error: str | None = None
            try:
                response = await self.forward(qreq)
                status_code = response.status_code
                response_json = response.json()
                if status_code >= 400:
                    error = json.dumps(response_json)[:500]
                    self.summary["failed"] += 1
                    qreq.future.set_result(JSONResponse(response_json, status_code=status_code))
                else:
                    self.summary["completed"] += 1
                    total_latency_s = time.time() - qreq.arrival_time
                    if total_latency_s <= qreq.slo_budget_s:
                        self.summary["slo_met"] += 1
                    qreq.future.set_result(JSONResponse(response_json, status_code=status_code))
            except Exception as exc:  # pragma: no cover - runtime safety
                error = repr(exc)
                self.summary["failed"] += 1
                qreq.future.set_result(JSONResponse({"error": error}, status_code=502))
            finally:
                end = time.time()
                service_s = end - start
                self.summary["total_queue_wait_s"] += queue_wait_s
                self.summary["total_service_s"] += service_s
                self.write_metric(
                    qreq=qreq,
                    worker_id=worker_id,
                    start_time=start,
                    end_time=end,
                    queue_wait_s=queue_wait_s,
                    service_s=service_s,
                    status_code=status_code,
                    response_json=response_json,
                    error=error,
                )
                self.queue.task_done()

    async def forward(self, qreq: QueuedRequest) -> httpx.Response:
        # Drop hop-by-hop headers. Preserve Authorization for upstream if present.
        headers = {}
        if "authorization" in qreq.headers:
            headers["authorization"] = qreq.headers["authorization"]
        return await self.client.post(
            f"{self.upstream_base_url}/chat/completions",
            json=qreq.body,
            headers=headers,
        )

    def write_metric(
        self,
        *,
        qreq: QueuedRequest,
        worker_id: int,
        start_time: float,
        end_time: float,
        queue_wait_s: float,
        service_s: float,
        status_code: int,
        response_json: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        usage = (response_json or {}).get("usage") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        total_latency_s = end_time - qreq.arrival_time
        row = {
            "request_id": qreq.request_id,
            "worker_id": worker_id,
            "policy": self.policy,
            "job_id": qreq.job_id,
            "resource_group": qreq.resource_group,
            "arrival_time": qreq.arrival_time,
            "start_time": start_time,
            "end_time": end_time,
            "queue_wait_s": queue_wait_s,
            "service_s": service_s,
            "total_latency_s": total_latency_s,
            "slo_budget_s": qreq.slo_budget_s,
            "slo_met": total_latency_s <= qreq.slo_budget_s,
            "cache_score": qreq.cache_score,
            "status_code": status_code,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cached_tokens": prompt_details.get("cached_tokens"),
            "error": error,
        }
        with open(self.metrics_jsonl, "a") as f:
            f.write(json.dumps(row) + "\n")


def infer_resource_group(body: dict[str, Any], extra: dict[str, Any]) -> str:
    explicit = extra.get("resource_group") or extra.get("this_func_call")
    if explicit:
        return str(explicit)
    messages = body.get("messages") or []
    if not messages:
        return "unknown"
    last = messages[-1]
    content = str(last.get("content", "")) if isinstance(last, dict) else str(last)
    lowered = content.lower()
    for token in ("open_file", "search", "get_all_symbols", "execute", "edit", "planner"):
        if token in lowered:
            return token
    return "llm_only"


def estimate_cache_score(body: dict[str, Any], extra: dict[str, Any]) -> float:
    if "cache_score" in extra:
        return float(extra["cache_score"])
    messages = body.get("messages") or []
    chars = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
    # Rough score in percentage-like units. Long prompts are more worth pinning.
    est_tokens = chars / 4.0
    if est_tokens >= 8000:
        return 40.0
    if est_tokens >= 4096:
        return 25.0
    if est_tokens >= 1024:
        return 10.0
    return 0.0


def create_app(proxy: SloQueueProxy) -> FastAPI:
    app = FastAPI(title="MONET Continuum SLO Queue Proxy")

    @app.on_event("startup")
    async def startup() -> None:
        await proxy.start()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "policy": proxy.policy, "workers": proxy.workers, "queue_size": proxy.queue.qsize()}

    @app.get("/metrics/summary")
    async def metrics_summary() -> dict[str, Any]:
        accepted = max(int(proxy.summary["accepted"]), 1)
        completed = max(int(proxy.summary["completed"]), 1)
        return {
            **proxy.summary,
            "queue_size": proxy.queue.qsize(),
            "avg_queue_wait_s": proxy.summary["total_queue_wait_s"] / accepted,
            "avg_service_s": proxy.summary["total_service_s"] / completed,
            "slo_met_rate": proxy.summary["slo_met"] / completed,
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, authorization: str | None = Header(default=None)) -> Any:
        body = await request.json()
        headers = {}
        if authorization:
            headers["authorization"] = authorization
        return await proxy.enqueue(body, headers)

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--policy", choices=["fcfs", "edf", "cache_aware_edf", "slack_cache"], default="cache_aware_edf")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument(
        "--metrics-jsonl",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "live_proxy_metrics.jsonl"),
    )
    args = parser.parse_args()

    proxy = SloQueueProxy(
        upstream_base_url=args.upstream,
        policy=args.policy,
        workers=args.workers,
        metrics_jsonl=args.metrics_jsonl,
        timeout_s=args.timeout_s,
    )
    app = create_app(proxy)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
