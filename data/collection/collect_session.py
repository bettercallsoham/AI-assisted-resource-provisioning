"""Capture non-overwriting, traceable Prometheus responses for one session."""

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collect_metrics import FIELDS, QUERIES

ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def query_raw(prometheus_url: str, query: str) -> dict:
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?{urlencode({'query': query})}"
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=10) as response:
        return json.load(response)


def complete_row(responses: dict[str, dict], max_skew: float, previous_timestamp: float | None,
                 observed_at: float | None = None) -> tuple[dict | None, str | None]:
    values = {}
    timestamps = []
    for field in FIELDS[1:]:
        payload = responses.get(field)
        if not payload or payload.get("status") != "success":
            return None, f"{field}: missing or failed query"
        results = payload.get("data", {}).get("result", [])
        if len(results) != 1 or "value" not in results[0]:
            return None, f"{field}: expected one Prometheus series"
        try:
            timestamp, value = results[0]["value"]
            timestamp, value = float(timestamp), float(value)
        except (TypeError, ValueError, IndexError):
            return None, f"{field}: invalid timestamp or value"
        if not math.isfinite(timestamp) or not math.isfinite(value) or value < 0:
            return None, f"{field}: nonfinite or negative measurement"
        timestamps.append(timestamp)
        values[field] = value
    if max(timestamps) - min(timestamps) > max_skew:
        return None, "query sample timestamps are too far apart"
    sample_time = max(timestamps)
    if observed_at is not None and abs(observed_at - sample_time) > max_skew:
        return None, "Prometheus sample is stale or ahead of collector clock"
    if previous_timestamp is not None and sample_time <= previous_timestamp:
        return None, "stale or duplicate Prometheus sample"
    values["timestamp"] = datetime.fromtimestamp(sample_time, tz=timezone.utc).isoformat()
    return {field: values[field] for field in FIELDS}, None


def git_revision() -> str | None:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def collect_session(session_id: str, role: str, output_root: Path, prometheus_url: str,
                    duration: float, interval: float, scenario: str, environment: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", session_id):
        raise ValueError("session-id must be a short name using letters, digits, '-' or '_'")
    if role not in ("development", "heldout") or duration <= 0 or interval <= 0:
        raise ValueError("role, duration or interval is invalid")
    output_root.mkdir(parents=True, exist_ok=True)
    directory = output_root / session_id
    directory.mkdir(exist_ok=False)
    raw_path = directory / "prometheus_responses.ndjson"
    csv_path = directory / "metrics.csv"
    manifest_path = directory / "manifest.json"
    manifest = {
        "session_id": session_id, "role": role, "status": "started",
        "started_at_utc": utc_now(), "ended_at_utc": None,
        "prometheus_url": prometheus_url, "environment": environment,
        "scenario": scenario, "duration_requested_seconds": duration,
        "poll_interval_requested_seconds": interval,
        "query_sample_max_skew_seconds": interval * 2,
        "queries": QUERIES,
        "units": {"request_rate": "requests/second", "cpu_utilization": "process CPU percent (may exceed 100 on multiple cores)",
                  "memory_utilization": "process RSS / effective memory limit * 100",
                  "network_throughput": "non-loopback network namespace sent+received B/s",
                  "response_latency": "milliseconds, 30-second request-weighted mean"},
        "collector_script_sha256": sha256(Path(__file__)),
        "metric_query_script_sha256": sha256(Path(__file__).with_name("collect_metrics.py")),
        "workload_app_sha256": sha256(ROOT / "workload-generator" / "app.py"),
        "workload_metric_semantics_sha256": sha256(ROOT / "workload-generator" / "metric_semantics.py"),
        "prometheus_config_sha256": sha256(ROOT / "monitoring" / "prometheus.yml"),
        "workload_scenario_script_sha256": sha256(Path(__file__).with_name("workload_scenario.py")),
        "git_revision": git_revision(), "collector_platform": platform.platform(),
        "polls": 0, "complete_rows": 0, "skipped_rows": 0, "skip_reasons": {},
    }
    previous_timestamp = None
    started = time.monotonic()
    next_poll = started
    try:
        with raw_path.open("x", encoding="utf-8") as raw_file, csv_path.open("x", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
            writer.writeheader()
            while time.monotonic() - started < duration:
                time.sleep(max(0.0, next_poll - time.monotonic()))
                next_poll += interval
                responses = {}
                errors = {}
                for field in FIELDS[1:]:
                    try:
                        responses[field] = query_raw(prometheus_url, QUERIES[field])
                    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                        errors[field] = str(error)
                raw_file.write(json.dumps({"polled_at_utc": utc_now(), "responses": responses,
                                           "errors": errors}, allow_nan=False) + "\n")
                raw_file.flush()
                manifest["polls"] += 1
                row, reason = complete_row(responses, interval * 2, previous_timestamp, time.time())
                if row is None:
                    manifest["skipped_rows"] += 1
                    manifest["skip_reasons"][reason] = manifest["skip_reasons"].get(reason, 0) + 1
                else:
                    writer.writerow(row)
                    csv_file.flush()
                    previous_timestamp = datetime.fromisoformat(row["timestamp"]).timestamp()
                    manifest["complete_rows"] += 1
            manifest["status"] = "complete"
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
    finally:
        manifest["ended_at_utc"] = utc_now()
        manifest["elapsed_seconds"] = time.monotonic() - started
        manifest["raw_sha256"] = sha256(raw_path)
        manifest["metrics_sha256"] = sha256(csv_path)
        scenario_log = directory / "scenario.jsonl"
        if scenario_log.is_file():
            manifest["scenario_log_sha256"] = sha256(scenario_log)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect one named, non-overwriting telemetry session")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--role", choices=("development", "heldout"), required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data" / "raw" / "sessions")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--scenario", required=True, help="Exact workload command or scenario notes")
    parser.add_argument("--environment", required=True, help="Workload environment and resource limits")
    args = parser.parse_args()
    result = collect_session(args.session_id, args.role, args.output_root,
                             args.prometheus_url, args.duration, args.interval,
                             args.scenario, args.environment)
    print(json.dumps(result, indent=2))
    if result["status"] != "complete" or result["complete_rows"] == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
