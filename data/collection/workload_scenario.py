"""Generate changing traffic against the Docker workload service."""

import argparse
import asyncio
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Phase:
    name: str
    rate: float


PHASES = (
    Phase("low", 2),
    Phase("medium", 8),
    Phase("high", 20),
    Phase("spike", 60),
    Phase("decrease", 8),
    Phase("mixed", 20),
)


async def send_request(client: httpx.AsyncClient, url: str) -> bool:
    try:
        response = await client.get(url)
        return response.is_success
    except httpx.HTTPError:
        return False


async def run(url: str, phase_duration: float) -> None:
    total = successful = failed = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for phase in PHASES:
            print(f"Starting phase: {phase.name} ({phase.rate:g} requests/sec)")
            phase_started = time.monotonic()
            budget = 0.0
            while time.monotonic() - phase_started < phase_duration:
                elapsed = time.monotonic() - phase_started
                rate = phase.rate
                if phase.name == "mixed":
                    rate = 3 if int(elapsed / 5) % 2 == 0 else 30
                budget += rate * 0.1
                request_count = int(budget)
                budget -= request_count
                if request_count:
                    results = await asyncio.gather(
                        *(send_request(client, url) for _ in range(request_count))
                    )
                    total += len(results)
                    successful += sum(results)
                    failed += len(results) - sum(results)
                await asyncio.sleep(0.1)
    print(f"Scenario complete: requests={total} successful={successful} failed={failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run low-to-spike workload phases")
    parser.add_argument("--url", default="http://localhost:8000/work")
    parser.add_argument("--phase-duration", type=float, default=30)
    args = parser.parse_args()
    if args.phase_duration <= 0:
        parser.error("--phase-duration must be positive")
    asyncio.run(run(args.url, args.phase_duration))


if __name__ == "__main__":
    main()