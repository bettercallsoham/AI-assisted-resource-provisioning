import os
import time
from datetime import datetime, timedelta, timezone

import httpx


PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")
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


def _query(query: str) -> float:
    payload = _get_json(f"{PROMETHEUS_URL.rstrip('/')}/api/v1/query", {"query": query})
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


def current_metrics() -> dict[str, float | str]:
    values = {name: _query(query) for name, query in METRIC_QUERIES.items()}
    values["timestamp"] = datetime.now(timezone.utc).isoformat()
    return values


def request_rate_history() -> list[float]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=90)
    query = METRIC_QUERIES["request_rate"]
    payload = _get_json(
        f"{PROMETHEUS_URL.rstrip('/')}/api/v1/query_range",
        {
            "query": query,
            "start": str(start.timestamp()),
            "end": str(end.timestamp()),
            "step": "5",
        },
    )
    results = payload.get("data", {}).get("result", [])
    if len(results) != 1:
        raise IntegrationError(f"Request-rate history returned {len(results)} series")
    values = []
    for _, raw_value in results[0].get("values", []):
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value == value and value not in (float("inf"), float("-inf")):
            values.append(value)
    if len(values) < 12:
        raise IntegrationError(f"Only {len(values)} request-rate history samples are available")
    return values[-12:]


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


def run_ml_pipeline() -> tuple[dict, dict, dict, dict]:
    metrics = current_metrics()
    history = request_rate_history()
    workload = post_ml("/predict/workload", {"history": history})
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
    return metrics, workload, resources, explanation