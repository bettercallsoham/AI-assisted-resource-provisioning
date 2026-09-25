import math
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI
import psutil
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

app = FastAPI(title="AI Provisioning Workload")
requests_total = Counter("workload_requests_total", "Total workload requests", ["endpoint", "status"])
request_latency = Histogram("workload_request_latency_seconds", "Workload request latency", ["endpoint"])
cpu_utilization = Gauge("workload_cpu_utilization_percent", "Workload process CPU utilization")
memory_utilization = Gauge("workload_memory_utilization_percent", "Workload container memory utilization")
network_throughput = Gauge("workload_network_throughput_bytes_per_second", "Workload network throughput")
process = psutil.Process(os.getpid())
last_network_bytes = None
last_network_time = None


def memory_limit() -> int:
	for current_path, limit_path in (
		("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
		("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes"),
	):
		try:
			limit_value = open(limit_path, encoding="ascii").read().strip()
			if limit_value != "max":
				return max(1, int(limit_value))
		except (FileNotFoundError, OSError, ValueError):
			continue
	return max(1, psutil.virtual_memory().total)


def update_resource_metrics() -> None:
	global last_network_bytes, last_network_time
	now = time.monotonic()
	process_cpu = process.cpu_percent(interval=None)
	process_memory = process.memory_info().rss / memory_limit() * 100
	network = psutil.net_io_counters()
	current_network_bytes = network.bytes_sent + network.bytes_recv
	if last_network_time is None or now <= last_network_time:
		throughput = 0.0
	else:
		throughput = max(0.0, (current_network_bytes - last_network_bytes) / (now - last_network_time))
	last_network_bytes = current_network_bytes
	last_network_time = now
	cpu_utilization.set(process_cpu)
	memory_utilization.set(process_memory)
	network_throughput.set(throughput)


@app.get("/")
def root() -> dict:
	return {"service": "workload", "status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
def health() -> dict:
	return {"status": "healthy"}


@app.get("/work")
def work(iterations: int = 120_000) -> dict:
	started = time.perf_counter()
	try:
		value = sum(math.sqrt(number) for number in range(max(1, min(iterations, 2_000_000))))
		elapsed = time.perf_counter() - started
		requests_total.labels("work", "success").inc()
		request_latency.labels("work").observe(elapsed)
		return {"status": "completed", "processing_time": elapsed, "result": round(value, 2), "timestamp": datetime.now(timezone.utc).isoformat()}
	except Exception:
		requests_total.labels("work", "error").inc()
		raise


@app.get("/metrics")
def metrics() -> Response:
	update_resource_metrics()
	return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
