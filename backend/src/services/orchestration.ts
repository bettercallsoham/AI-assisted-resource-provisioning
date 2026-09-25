import type { Host, Metrics, Snapshot } from "../types/index.js";

const prometheusUrl = process.env.PROMETHEUS_URL ?? "http://localhost:9090";
const mlUrl = process.env.ML_SERVICE_URL ?? "http://localhost:8001";
const decisionUrl = process.env.DECISION_ENGINE_URL ?? "http://localhost:8002";
const hosts: Host[] = [
  { id: "Host-01", total_cpu: 8, total_memory: 16, total_network: 1000, allocated_cpu: 2, allocated_memory: 4, allocated_network: 100 },
  { id: "Host-02", total_cpu: 12, total_memory: 32, total_network: 1000, allocated_cpu: 5, allocated_memory: 10, allocated_network: 220 },
  { id: "Host-03", total_cpu: 16, total_memory: 32, total_network: 10000, allocated_cpu: 3, allocated_memory: 8, allocated_network: 400 }
];
const events: Array<Record<string, unknown>> = [];
const history: Array<{ timestamp: string; actual: number; predicted: number }> = [];

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json() as Promise<T>;
}

async function query(promql: string): Promise<number | null> {
  try {
    const result = await json<{ data?: { result?: Array<{ value: [number, string] }> } }>(`${prometheusUrl}/api/v1/query?query=${encodeURIComponent(promql)}`);
    const value = result.data?.result?.[0]?.value?.[1];
    return value === undefined ? null : Number(value);
  } catch { return null; }
}

async function metrics(): Promise<Metrics> {
  const [requestRate, cpu, memory, network, latency] = await Promise.all([
    query("sum(rate(workload_requests_total{endpoint=\"work\",status=\"success\"}[30s]))"),
    query("workload_cpu_utilization_percent"),
    query("workload_memory_utilization_percent"),
    query("workload_network_throughput_bytes_per_second"),
    query("1000 * sum(rate(workload_request_latency_seconds_sum{endpoint=\"work\"}[30s])) / sum(rate(workload_request_latency_seconds_count{endpoint=\"work\"}[30s]))")
  ]);
  return { requestRate, cpu, memory, network, latency, timestamp: new Date().toISOString() };
}

function addEvent(eventType: string, message: string, details: Record<string, unknown> = {}) {
  events.unshift({ timestamp: new Date().toISOString(), event_type: eventType, message, details });
  events.splice(20);
}

export async function getSnapshot(): Promise<Snapshot> {
  const snapshot: Snapshot = { metrics: { requestRate: null, cpu: null, memory: null, network: null, latency: null, timestamp: new Date().toISOString() }, prediction: null, resources: null, decision: null, placement: null, explanation: null, hosts, history: [...history], errors: [], events };
  try {
    const live = await json<{ current_metrics: { request_rate: number; cpu: number; memory: number; network: number; latency: number; timestamp: string }; predicted_workload: { predicted_request_rate: number; model: string }; predicted_cpu: number; predicted_memory: number; predicted_network: number; decision: string; reason: string; capacity_status: Record<string, unknown>; placement: Record<string, unknown>; explanation: Record<string, unknown> }>(`${decisionUrl}/decision/live`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hosts, vms: [{ id: "VM-01", cpu_required: 2, memory_required: 4, network_required: 100 }, { id: "VM-02", cpu_required: 3, memory_required: 6, network_required: 150 }, { id: "VM-03", cpu_required: 1, memory_required: 2, network_required: 50 }] }) });
    snapshot.metrics = { requestRate: live.current_metrics.request_rate, cpu: live.current_metrics.cpu, memory: live.current_metrics.memory, network: live.current_metrics.network, latency: live.current_metrics.latency, timestamp: live.current_metrics.timestamp };
    snapshot.prediction = live.predicted_workload;
    snapshot.resources = { predicted_cpu: live.predicted_cpu, predicted_memory: live.predicted_memory, predicted_network: live.predicted_network };
    snapshot.decision = { decision: live.decision, reason: live.reason, ...live.capacity_status };
    snapshot.placement = live.placement;
    snapshot.explanation = live.explanation;
    history.push({ timestamp: live.current_metrics.timestamp, actual: live.current_metrics.request_rate, predicted: live.predicted_workload.predicted_request_rate });
    if (history.length > 30) history.shift();
    snapshot.history = [...history];
    addEvent("LIVE_METRICS", "Prometheus observation received", snapshot.metrics);
    addEvent("LSTM_PREDICTION", "Workload forecast updated", live.predicted_workload);
    addEvent("RESOURCE_ESTIMATION", "Random Forest demand estimated", snapshot.resources);
    addEvent("DECISION", live.reason, { decision: live.decision });
    addEvent("PLACEMENT", "Best-Fit placement evaluated", live.placement);
  } catch (error) { snapshot.errors.push(error instanceof Error ? error.message : "Service request failed"); }
  return snapshot;
}

export { metrics, events, hosts };