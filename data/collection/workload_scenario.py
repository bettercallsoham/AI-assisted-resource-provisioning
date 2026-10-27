"""Run the shared changing-traffic scenario against the workload service."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workload-generator"))
from scenarios import Phase, run_phases


PHASES = (
    ("low", 2), ("medium", 8), ("high", 20), ("spike", 60),
    ("decrease", 8), ("mixed", 20),
)


async def run(url: str, phase_duration: float, event_log: Path | None = None) -> None:
    log = event_log.open("x", encoding="utf-8") if event_log else None

    def record(event: dict) -> None:
        if event["event"] == "phase_start":
            print(f"Starting phase: {event['phase']} ({event['nominal_rate_requests_per_second']:g} requests/sec)")
        if log:
            log.write(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(), **event}) + "\n")
            log.flush()

    try:
        totals = await run_phases(url, tuple(Phase(name, rate, phase_duration) for name, rate in PHASES),
                                  on_event=record)
    finally:
        if log:
            log.close()
    print(f"Scenario complete: requests={totals['requests']} successful={totals['successful']} failed={totals['failed']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run low-to-spike workload phases")
    parser.add_argument("--url", default="http://localhost:8000/work")
    parser.add_argument("--phase-duration", type=float, default=30)
    parser.add_argument("--event-log", type=Path, help="New JSONL file for actual phase times and request counts")
    args = parser.parse_args()
    if args.phase_duration <= 0:
        parser.error("--phase-duration must be positive")
    asyncio.run(run(args.url, args.phase_duration, args.event_log))


if __name__ == "__main__":
    main()
