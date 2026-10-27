import argparse
import asyncio
import time
from datetime import datetime, timezone

import httpx


async def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    sent = successful = failed = 0
    latencies: list[float] = []
    budget = 0.0
    async with httpx.AsyncClient(timeout=10) as client:
        while time.perf_counter() - started < args.duration:
            elapsed = time.perf_counter() - started
            rate = args.rate
            if args.scenario:
                progress = elapsed / args.duration
                rate = args.rate * (1 + min(progress * 2, 2)) if progress < 0.7 else args.rate
            if args.spike and elapsed > args.duration / 2:
                rate *= 4
            budget += rate * 0.1
            batch = int(budget)
            budget -= batch
            batch_started = time.perf_counter()
            results = await asyncio.gather(*(send(client, args.url) for _ in range(batch))) if batch else []
            for latency, ok in results:
                sent += 1
                (latencies if ok else []).append(latency)
                successful += int(ok)
                failed += int(not ok)
            await asyncio.sleep(max(0, 0.1 - (time.perf_counter() - batch_started)))
    average = sum(latencies) / len(latencies) if latencies else 0
    print(f"{datetime.now(timezone.utc).isoformat()} requests={sent} successful={successful} failed={failed} average_latency={average:.4f}s")


async def send(client: httpx.AsyncClient, url: str) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        response = await client.get(url)
        return time.perf_counter() - started, response.is_success
    except httpx.HTTPError:
        return time.perf_counter() - started, False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate controlled workload traffic")
    parser.add_argument("--url", default="http://localhost:8000/work")
    parser.add_argument("--rate", type=float, default=5)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--spike", action="store_true")
    parser.add_argument("--scenario", action="store_true", help="normal, increase, high load, decrease")
    args = parser.parse_args()
    if args.rate <= 0 or args.duration <= 0:
        parser.error("--rate and --duration must be positive")
    asyncio.run(run(args))
