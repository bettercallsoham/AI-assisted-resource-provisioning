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
const history: number[] = [];

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
    query("rate(workload_requests_total{status=\"success\"}[1m])"),
    query("100 * avg(rate(container_cpu_usage_seconds_total{name=\"workload\"}[1m]))"),
    query("container_memory_usage_bytes{name=\"workload\"}"),
    query("rate(container_network_receive_bytes_total{name=\"workload\"}[1m])"),
    query("rate(workload_request_latency_seconds_sum[1m]) / rate(workload_request_latency_seconds_count[1m])")
  ]);
  return { requestRate, cpu, memory, network, latency, timestamp: new Date().toISOString() };
}

function addEvent(eventType: string, message: string, details: Record<string, unknown> = {}) {
  events.unshift({ timestamp: new Date().toISOString(), event_type: eventType, message, details });
  events.splice(20);
}

export async function getSnapshot(): Promise<Snapshot> {
  const observed = await metrics();
  const currentRate = observed.requestRate ?? 0;
  history.push(currentRate);
  if (history.length > 20) history.shift();
  const snapshot: Snapshot = { metrics: observed, prediction: null, resources: null, decision: null, placement: null, explanation: null, errors: [], events };
  if (history.length < 3) snapshot.errors.push("Waiting for at least three observed request-rate samples");
  try {
    const prediction = await json<{ predicted_request_rate: number; model: string }>(`${mlUrl}/predict/workload`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ history: history.length >= 3 ? history : [0, 0, 0] }) });
    snapshot.prediction = prediction;
    addEvent("LSTM_PREDICTION", "Workload forecast updated", prediction);
    const request = { predicted_request_rate: prediction.predicted_request_rate, current_request_rate: currentRate, cpu_utilization: observed.cpu ?? 0, memory_utilization: observed.memory ?? 0, network_throughput: observed.network ?? 0, response_latency: observed.latency ?? 0 };
    const resources = await json<{ predicted_cpu: number; predicted_memory: number; predicted_network: number }>(`${mlUrl}/predict/resources`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
    snapshot.resources = resources;
    snapshot.explanation = await json(`${mlUrl}/explain/resources`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
    snapshot.decision = await json(`${decisionUrl}/decision`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hosts, predicted: { cpu: resources.predicted_cpu, memory: resources.predicted_memory, network: resources.predicted_network } }) });
    snapshot.placement = await json(`${decisionUrl}/placement`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hosts, vms: [{ id: "VM-01", cpu_required: 2, memory_required: 4, network_required: 100 }, { id: "VM-02", cpu_required: 3, memory_required: 6, network_required: 150 }, { id: "VM-03", cpu_required: 1, memory_required: 2, network_required: 50 }], predicted: { cpu: 0, memory: 0, network: 0 } }) });
  } catch (error) { snapshot.errors.push(error instanceof Error ? error.message : "Service request failed"); }
  return snapshot;
}

export { metrics, events, hosts };