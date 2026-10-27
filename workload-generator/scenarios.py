"""Bounded HTTP workload scenarios shared by the CLI and demo controller."""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

import httpx


@dataclass(frozen=True)
class Phase:
    name: str
    rate: float
    duration: float


async def send_request(client: httpx.AsyncClient, url: str) -> bool:
    try:
        return (await client.get(url)).is_success
    except httpx.HTTPError:
        return False


async def run_phases(url: str, phases: tuple[Phase, ...], stop: asyncio.Event | None = None,
                     on_event: Callable[[dict], None] | None = None) -> dict[str, int | bool]:
    totals: dict[str, int | bool] = {"requests": 0, "successful": 0, "failed": 0, "stopped": False}

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    async with httpx.AsyncClient(timeout=10) as client:
        for phase in phases:
            if stop and stop.is_set():
                totals["stopped"] = True
                break
            emit({"event": "phase_start", "phase": phase.name,
                  "nominal_rate_requests_per_second": phase.rate})
            started = time.monotonic()
            budget = 0.0
            requests = successful = 0
            last_report = started
            while time.monotonic() - started < phase.duration:
                if stop and stop.is_set():
                    totals["stopped"] = True
                    break
                elapsed = time.monotonic() - started
                rate = phase.rate
                if phase.name == "mixed":
                    rate = 3 if int(elapsed / 5) % 2 == 0 else 30
                budget += rate * 0.1
                count = int(budget)
                budget -= count
                tick = time.monotonic()
                if count:
                    results = await asyncio.gather(*(send_request(client, url) for _ in range(count)))
                    requests += len(results)
                    successful += sum(results)
                if time.monotonic() - last_report >= 1:
                    emit({"event": "progress", "phase": phase.name,
                          "requests": requests, "successful": successful,
                          "failed": requests - successful})
                    last_report = time.monotonic()
                await asyncio.sleep(max(0.0, 0.1 - (time.monotonic() - tick)))
            failed = requests - successful
            totals["requests"] += requests
            totals["successful"] += successful
            totals["failed"] += failed
            emit({"event": "phase_end", "phase": phase.name,
                  "elapsed_seconds": time.monotonic() - started,
                  "requests": requests, "successful": successful, "failed": failed})
            if totals["stopped"]:
                break
    return totals
