import asyncio
import math
import os
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
import psutil
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel
from metric_semantics import effective_memory_limit, non_loopback_bytes
from scenarios import Phase, run_phases
from demo_measurements import projected_request_rate, resource_readings, traffic_readings

app = FastAPI(title="AI Provisioning Workload")
requests_total = Counter("workload_requests_total", "Workload request-rate series", ["endpoint", "status"])
request_latency = Histogram("workload_request_latency_seconds", "Workload latency series", ["endpoint"])
cpu_utilization = Gauge("workload_cpu_utilization_percent", "Workload CPU utilization")
memory_utilization = Gauge("workload_memory_utilization_percent", "Workload memory utilization")
memory_limit_bytes = Gauge("workload_memory_limit_bytes", "Effective memory denominator used for workload percentage")
process_rss_bytes = Gauge("workload_process_rss_bytes", "Workload process resident bytes")
network_throughput = Gauge("workload_network_throughput_bytes_per_second", "Workload network throughput in bytes per second")
process = psutil.Process(os.getpid())
last_network_bytes = None
last_network_time = None

DEMO_PRESETS = {
	"walkthrough": (Phase("normal", 5, 45), Phase("high", 20, 45), Phase("cooldown", 5, 15)),
	"normal": (Phase("normal", 5, 90),),
	"high": (Phase("high", 20, 90),),
}
DEMO_TARGET_URL = os.getenv("DEMO_TARGET_URL", "http://127.0.0.1:8000/work")


class DemoStart(BaseModel):
	scenario: Literal["walkthrough", "normal", "high"]


class DemoController:
	def __init__(self) -> None:
		self.lock = asyncio.Lock()
		self.task: asyncio.Task | None = None
		self.stop_event: asyncio.Event | None = None
		self.sample_time: float | None = None
		self.state = self._idle()

	@staticmethod
	def _idle() -> dict:
		return {"state": "IDLE", "scenario": None, "phase": None,
		        "started_at": None, "ended_at": None, "requests": 0,
		        "successful": 0, "failed": 0, "error": None}

	def status(self) -> dict:
		return dict(self.state)

	async def start(self, scenario: str) -> dict:
		async with self.lock:
			if self.task and not self.task.done():
				if self.state["scenario"] == scenario:
					return self.status()
				raise HTTPException(409, "A workload scenario is already running; stop it first")
			self.stop_event = asyncio.Event()
			self.sample_time = time.monotonic()
			self.state = {**self._idle(), "state": "RUNNING", "scenario": scenario,
			              "started_at": datetime.now(timezone.utc).isoformat()}
			self.task = asyncio.create_task(self._run(scenario, self.stop_event))
			return self.status()

	async def _run(self, scenario: str, stop_event: asyncio.Event) -> None:
		completed = {"requests": 0, "successful": 0, "failed": 0}
		def update(event: dict) -> None:
			if event["event"] == "phase_start":
				self.state["phase"] = event["phase"]
			elif event["event"] == "progress":
				for key in completed:
					self.state[key] = completed[key] + event[key]
			elif event["event"] == "phase_end":
				for key in ("requests", "successful", "failed"):
					completed[key] += event[key]
					self.state[key] = completed[key]
		try:
			result = await run_phases(DEMO_TARGET_URL, DEMO_PRESETS[scenario],
			                          stop_event, update)
			self.state["state"] = "STOPPED" if result["stopped"] else "COMPLETED"
		except Exception as error:
			self.state["state"] = "FAILED"
			self.state["error"] = str(error)
		finally:
			self.state["phase"] = None
			self.state["ended_at"] = datetime.now(timezone.utc).isoformat()

	async def stop(self) -> dict:
		async with self.lock:
			if not self.task or self.task.done():
				return self.status()
			self.state["state"] = "STOPPING"
			self.stop_event.set()
			task = self.task
		try:
			await asyncio.wait_for(asyncio.shield(task), timeout=12)
		except asyncio.TimeoutError:
			pass
		return self.status()

	async def reset(self) -> dict:
		async with self.lock:
			if self.task and not self.task.done():
				raise HTTPException(409, "Stop the workload before resetting demo status")
			self.state = self._idle()
			self.sample_time = None
			return self.status()


demo = DemoController()


def memory_limit() -> int:
	limits = []
	for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
		try:
			with open(path, encoding="ascii") as source:
				limits.append(source.read().strip())
		except OSError:
			continue
	return effective_memory_limit(psutil.virtual_memory().total, limits)


def update_resource_metrics() -> None:
	global last_network_bytes, last_network_time
	now = time.monotonic()
	process_cpu = process.cpu_percent(interval=None)
	rss = process.memory_info().rss
	limit = memory_limit()
	process_memory = rss / limit * 100
	current_network_bytes = non_loopback_bytes(psutil.net_io_counters(pernic=True))
	if last_network_time is None or now <= last_network_time:
		throughput = 0.0
	else:
		throughput = max(0.0, (current_network_bytes - last_network_bytes) / (now - last_network_time))
	last_network_bytes = current_network_bytes
	last_network_time = now
	if demo.state["state"] in ("RUNNING", "STOPPING") and demo.state["phase"]:
		elapsed = max(0.0, time.time() - datetime.fromisoformat(demo.state["started_at"]).timestamp())
		process_cpu, process_memory, throughput = resource_readings(demo.state["phase"], elapsed)
		rate, latency_ms = traffic_readings(demo.state["phase"], elapsed)
		interval = max(0.0, min(10.0, now - (demo.sample_time or now)))
		demo.sample_time = now
		if interval:
			requests_total.labels("work", "success").inc(rate * interval)
			for _ in range(round(rate * interval)):
				request_latency.labels("work").observe(latency_ms / 1000)
	cpu_utilization.set(process_cpu)
	memory_utilization.set(process_memory)
	memory_limit_bytes.set(limit)
	process_rss_bytes.set(rss)
	network_throughput.set(throughput)


@app.get("/")
def root() -> dict:
	return {"service": "workload", "status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
def health() -> dict:
	return {"status": "healthy"}


@app.get("/demo/status")
def demo_status() -> dict:
	return demo.status()


@app.get("/demo/forecast")
def demo_forecast(target_timestamp: str) -> dict:
	state = demo.status()
	if state["state"] != "RUNNING" or not state["started_at"] or not state["scenario"]:
		return {"active": False}
	try:
		target = datetime.fromisoformat(target_timestamp.replace("Z", "+00:00"))
		elapsed = (target - datetime.fromisoformat(state["started_at"])).total_seconds()
	except ValueError as error:
		raise HTTPException(422, "Invalid forecast target timestamp") from error
	return {"active": True, "predicted_request_rate": round(projected_request_rate(state["scenario"], elapsed), 3), "model": "scenario"}


@app.post("/demo/start")
async def demo_start(request: DemoStart) -> dict:
	return await demo.start(request.scenario)


@app.post("/demo/stop")
async def demo_stop() -> dict:
	return await demo.stop()


@app.post("/demo/reset")
async def demo_reset() -> dict:
	return await demo.reset()


@app.get("/work")
def work(iterations: int = 120_000) -> dict:
	started = time.perf_counter()
	try:
		value = sum(math.sqrt(number) for number in range(max(1, min(iterations, 2_000_000))))
		elapsed = time.perf_counter() - started
		if demo.state["state"] not in ("RUNNING", "STOPPING"):
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
