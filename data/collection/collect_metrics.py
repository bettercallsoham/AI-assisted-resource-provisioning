"""Collect live workload measurements from Prometheus into a CSV file."""

import argparse
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FIELDS = [
    "timestamp",
    "request_rate",
    "cpu_utilization",
    "memory_utilization",
    "network_throughput",
    "response_latency",
]

QUERIES = {
    "request_rate": 'sum(rate(workload_requests_total{endpoint="work",status="success"}[30s]))',
    "cpu_utilization": "workload_cpu_utilization_percent",
    "memory_utilization": "workload_memory_utilization_percent",
    "network_throughput": "workload_network_throughput_bytes_per_second",
    "response_latency": (
        '1000 * sum(rate(workload_request_latency_seconds_sum'
        '{endpoint="work"}[30s]))'
        ' / sum(rate(workload_request_latency_seconds_count'
        '{endpoint="work"}[30s]))'
    ),
}


class MetricUnavailable(RuntimeError):
    """Raised when Prometheus cannot provide a required live measurement."""


def query_prometheus(prometheus_url: str, query: str) -> tuple[float, float]:
    endpoint = f"{prometheus_url.rstrip('/')}/api/v1/query?{urlencode({'query': query})}"
    request = Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise MetricUnavailable(f"Prometheus query failed: {error}") from error

    if payload.get("status") != "success":
        raise MetricUnavailable(f"Prometheus rejected query: {payload}")
    results = payload.get("data", {}).get("result", [])
    if len(results) != 1 or "value" not in results[0]:
        raise MetricUnavailable(f"query returned {len(results)} series")
    timestamp, value = results[0]["value"]
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as error:
        raise MetricUnavailable(f"query returned a non-numeric value: {value}") from error
    if not math.isfinite(numeric_value):
        raise MetricUnavailable(f"query returned a non-finite value: {value}")
    return float(timestamp), numeric_value


def collect_once(prometheus_url: str) -> dict[str, float | str]:
    measurements: dict[str, float | str] = {}
    sample_timestamps = []
    for field in FIELDS[1:]:
        sample_timestamp, value = query_prometheus(prometheus_url, QUERIES[field])
        sample_timestamps.append(sample_timestamp)
        measurements[field] = value
    measurements["timestamp"] = datetime.fromtimestamp(
        max(sample_timestamps), tz=timezone.utc
    ).isoformat()
    return {field: measurements[field] for field in FIELDS}


def collect(prometheus_url: str, output: Path, duration: float, interval: float) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rows_written = 0
    with output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        while time.monotonic() - started < duration:
            try:
                row = collect_once(prometheus_url)
            except MetricUnavailable as error:
                print(f"Waiting for live metrics: {error}")
            else:
                writer.writerow(row)
                csv_file.flush()
                rows_written += 1
                print(f"Collected {row['timestamp']} ({rows_written} rows)")

            time.sleep(interval)
    return rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect live Prometheus workload metrics")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--output", type=Path, default=Path("data/raw/metrics.csv"))
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0:
        parser.error("--duration and --interval must be positive")
    rows_written = collect(args.prometheus_url, args.output, args.duration, args.interval)
    print(f"Saved {rows_written} real Prometheus rows to {args.output}")


if __name__ == "__main__":
    main()