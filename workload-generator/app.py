import math
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from prometheus_client import Counter, Histogram, make_asgi_app

app = FastAPI(title="AI Provisioning Workload")
requests_total = Counter("workload_requests_total", "Total workload requests", ["endpoint", "status"])
request_latency = Histogram("workload_request_latency_seconds", "Workload request latency", ["endpoint"])


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


app.mount("/metrics", make_asgi_app())
