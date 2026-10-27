"""Repeatable resource readings for the bounded demo scenarios."""

import math


def resource_readings(phase: str, elapsed: float) -> tuple[float, float, float]:
    baselines = {
        "normal": (28.0, 36.0, 62_000.0),
        "high": (76.0, 68.0, 410_000.0),
        "cooldown": (19.0, 31.0, 38_000.0),
    }
    cpu, memory, network = baselines.get(phase, baselines["normal"])
    wave = math.sin(elapsed * 0.42) + 0.35 * math.sin(elapsed * 1.13)
    return (
        max(0.0, min(100.0, cpu + 4.5 * wave)),
        max(0.0, min(100.0, memory + 1.8 * wave)),
        max(0.0, network * (1.0 + 0.09 * wave)),
    )


def traffic_readings(phase: str, elapsed: float) -> tuple[float, float]:
    rate, latency_ms = {
        "normal": (5.0, 32.0),
        "high": (20.0, 135.0),
        "cooldown": (5.0, 26.0),
    }.get(phase, (5.0, 32.0))
    wave = math.sin(elapsed * 0.42) + 0.35 * math.sin(elapsed * 1.13)
    return max(0.1, rate * (1.0 + 0.08 * wave)), max(1.0, latency_ms * (1.0 + 0.06 * wave))


def projected_request_rate(scenario: str, elapsed: float, window: float = 30.0) -> float:
    """Project the same rolling rate displayed by Prometheus at a future time."""
    phases = {
        "walkthrough": (("normal", 45.0), ("high", 45.0), ("cooldown", 15.0)),
        "normal": (("normal", 90.0),),
        "high": (("high", 90.0),),
    }[scenario]
    if elapsed <= 0:
        return 0.0
    start = max(0.0, elapsed - window)
    step = 0.5
    total = 0.0
    position = start
    while position < elapsed:
        end = min(elapsed, position + step)
        midpoint = (position + end) / 2
        phase_start = 0.0
        for name, duration in phases:
            if midpoint < phase_start + duration:
                if midpoint >= phase_start:
                    total += traffic_readings(name, midpoint)[0] * (end - position)
                break
            phase_start += duration
        position = end
    return total / window
