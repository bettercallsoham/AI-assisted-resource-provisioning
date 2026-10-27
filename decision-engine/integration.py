import os
import time
import math
from datetime import datetime, timedelta, timezone

import httpx


PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")
WORKLOAD_URL = os.getenv("WORKLOAD_URL", "http://localhost:8000")
METRIC_QUERIES = {
    "request_rate": 'sum(rate(workload_requests_total{endpoint="work",status="success"}[30s]))',
    "cpu": "workload_cpu_utilization_percent",
    "memory": "workload_memory_utilization_percent",
    "network": "workload_network_throughput_bytes_per_second",
    "latency": '1000 * sum(rate(workload_request_latency_seconds_sum{endpoint="work"}[30s])) / sum(rate(workload_request_latency_seconds_count{endpoint="work"}[30s]))',
}


class IntegrationError(RuntimeError):
    pass


def _get_json(url: str, params: dict[str, str] | None = None) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise IntegrationError(f"Request failed for {url}: {error}") from error


def _query(query: str, at: float | None = None) -> float:
    params = {"query": query}
    if at is not None:
        params["time"] = str(at)
    payload = _get_json(f"{PROMETHEUS_URL.rstrip('/')}/api/v1/query", params)
    results = payload.get("data", {}).get("result", [])
    if len(results) != 1:
        raise IntegrationError(f"Prometheus query returned {len(results)} series: {query}")
    value = results[0].get("value", [None, None])[1]
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise IntegrationError(f"Prometheus returned a non-numeric value: {value}") from error
    if number != number or number in (float("inf"), float("-inf")):
        raise IntegrationError(f"Prometheus returned a non-finite value for: {query}")
    return number


def current_metrics(origin: dict) -> dict[str, float | str]:
    at = datetime.fromisoformat(origin["timestamp"]).timestamp()
    values = {name: _query(query, at) for name, query in METRIC_QUERIES.items()
              if name != "request_rate"}
    values["request_rate"] = origin["value"]
    values["timestamp"] = origin["timestamp"]
    return values


def request_rate_history() -> list[dict[str, float | str]]:
    now = time.time()
    # Allow the five-second scrape to finish; use the same grid on every poll.
    end = math.floor((now - 3) / 5) * 5
    start = end - 55
    query = METRIC_QUERIES["request_rate"]
    payload = _get_json(
        f"{PROMETHEUS_URL.rstrip('/')}/api/v1/query_range",
        {
            "query": query,
            "start": str(start),
            "end": str(end),
            "step": "5",
        },
    )
    results = payload.get("data", {}).get("result", [])
    if len(results) != 1:
        raise IntegrationError(f"Request-rate history returned {len(results)} series")
    values = []
    for raw_timestamp, raw_value in results[0].get("values", []):
        try:
            timestamp = float(raw_timestamp)
            value = float(raw_value)
        except (TypeError, ValueError):
            raise IntegrationError("Request-rate history contains a non-numeric sample")
        if not math.isfinite(timestamp) or not math.isfinite(value) or value < 0:
            raise IntegrationError("Request-rate history contains an invalid sample")
        values.append({"timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                       "value": value})
    if len(values) != 12 or any(abs(datetime.fromisoformat(values[index]["timestamp"]).timestamp()
                                   - (start + index * 5)) > 0.01 for index in range(12)):
        raise IntegrationError("A complete, aligned five-second request-rate history is unavailable")
    scraped_at = _query('timestamp(workload_requests_total{endpoint="work",status="success"})', end)
    if scraped_at > now + 1 or now - scraped_at > 12:
        raise IntegrationError("Workload counter sample is stale")
    return values


def post_ml(path: str, body: dict) -> dict:
    payload = _get_json(f"{ML_SERVICE_URL.rstrip('/')}{path}") if body is None else None
    if body is not None:
        try:
            response = httpx.post(f"{ML_SERVICE_URL.rstrip('/')}{path}", json=body, timeout=120)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise IntegrationError(f"ML request failed for {path}: {error}") from error
    return payload


def planned_workload(target: datetime) -> dict | None:
    try:
        response = httpx.get(
            f"{WORKLOAD_URL.rstrip('/')}/demo/forecast",
            params={"target_timestamp": target.isoformat()}, timeout=2,
        )
        response.raise_for_status()
        forecast = response.json()
        rate = float(forecast.get("predicted_request_rate"))
        if forecast.get("active") and math.isfinite(rate) and rate >= 0:
            return {"predicted_request_rate": rate, "model": "scenario"}
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        pass
    return None


def run_ml_pipeline() -> tuple[dict, dict, dict, dict, list[dict]]:
    history = request_rate_history()
    metrics = current_metrics(history[-1])
    origin = datetime.fromisoformat(history[-1]["timestamp"])
    workload = planned_workload(origin + timedelta(seconds=5))
    if workload is None:
        workload = post_ml("/predict/workload", {"history": [point["value"] for point in history]})
    workload["origin_timestamp"] = origin.isoformat()
    workload["target_timestamp"] = (origin + timedelta(seconds=5)).isoformat()
    resource_input = {
        "predicted_request_rate": workload["predicted_request_rate"],
        "current_request_rate": metrics["request_rate"],
        "cpu_utilization": metrics["cpu"],
        "memory_utilization": metrics["memory"],
        "network_throughput": metrics["network"],
        "response_latency": metrics["latency"],
    }
    resources = post_ml("/predict/resources", resource_input)
    explanation = post_ml("/explain/resources", resource_input)
    return metrics, workload, resources, explanation, history
