import type { Host, Metrics, Snapshot } from "../types/index.js";
import { provisioner } from "./provisioning.js";
import type { DecisionPlan, VMRequest } from "./provisioning.js";
import { mergeForecastHistory } from "./forecastHistory.js";
import type { ForecastPoint } from "./forecastHistory.js";

const prometheusUrl = process.env.PROMETHEUS_URL ?? "http://localhost:9090";
const mlUrl = process.env.ML_SERVICE_URL ?? "http://localhost:8001";
const decisionUrl = process.env.DECISION_ENGINE_URL ?? "http://localhost:8002";
const events: Array<Record<string, unknown>> = [];
let history: ForecastPoint[] = [];

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${url} returned ${response.status}: ${(await response.text()).slice(0, 300)}`);
  return response.json() as Promise<T>;
}

async function query(promql: string): Promise<number | null> {
  try {
    const result = await json<{ data?: { result?: Array<{ value: [number, string] }> } }>(`${prometheusUrl}/api/v1/query?query=${encodeURIComponent(promql)}`);
    const value = result.data?.result?.[0]?.value?.[1];
    const parsed = value === undefined ? null : Number(value);
    return parsed !== null && Number.isFinite(parsed) ? parsed : null;
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

export function addEvent(eventType: string, message: string, details: Record<string, unknown> = {}) {
  events.unshift({ timestamp: new Date().toISOString(), event_type: eventType, message, details });
  events.splice(20);
}

export function clearDemoHistory(): void {
  events.length = 0;
  history.length = 0;
}

function recordObservation(timestamp: string, actual: number | null): void {
  if (actual === null || !Number.isFinite(actual)) return;
  history = mergeForecastHistory(history, [{ timestamp, value: actual }], null);
}

export async function getSnapshot(): Promise<Snapshot> {
  const hosts = provisioner.hosts();
  const proposal = provisioner.latest();
  const proposalVersion = `${proposal?.id}:${proposal?.status}:${proposal?.updated_at}`;
  const vms = proposal?.status === "PENDING_APPROVAL" ? proposal.vms : [];
  const snapshot: Snapshot = { metrics: { requestRate: null, cpu: null, memory: null, network: null, latency: null, timestamp: new Date().toISOString() }, prediction: null, resources: null, decision: null, placement: null, explanation: null, proposal, hosts, history: [...history], errors: [], events };
  try {
    const live = await json<{ current_metrics: { request_rate: number; cpu: number; memory: number; network: number; latency: number; timestamp: string }; predicted_workload: { predicted_request_rate: number; model: string; origin_timestamp: string; target_timestamp: string }; request_history: Array<{ timestamp: string; value: number }>; predicted_cpu: number; predicted_memory: number; predicted_network: number; decision: string; reason: string; capacity_status: Record<string, unknown>; placement: Record<string, unknown>; explanation: Record<string, unknown> }>(`${decisionUrl}/decision/live`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hosts, vms }) });
    snapshot.metrics = { requestRate: live.current_metrics.request_rate, cpu: live.current_metrics.cpu, memory: live.current_metrics.memory, network: live.current_metrics.network, latency: live.current_metrics.latency, timestamp: live.current_metrics.timestamp };
    snapshot.prediction = live.predicted_workload;
    snapshot.resources = { predicted_cpu: live.predicted_cpu, predicted_memory: live.predicted_memory, predicted_network: live.predicted_network };
    snapshot.decision = { decision: live.decision, reason: live.reason, ...live.capacity_status };
    snapshot.placement = live.placement;
    snapshot.explanation = live.explanation;
    history = mergeForecastHistory(history, live.request_history, live.predicted_workload);
    snapshot.history = [...history];
    addEvent("LIVE_METRICS", "Prometheus observation received", snapshot.metrics);
    addEvent("WORKLOAD_FORECAST", "Workload forecast updated", live.predicted_workload);
    addEvent("RESOURCE_ESTIMATION", "Random Forest demand estimated", snapshot.resources);
    addEvent("DECISION", live.reason, { decision: live.decision });
    addEvent("PLACEMENT", "Best-Fit placement evaluated", live.placement);
  } catch (error) {
    snapshot.errors.push(error instanceof Error ? error.message : "Live prediction failed");
    try {
      const plan = await evaluatePlan(hosts, vms);
      snapshot.decision = plan;
      snapshot.placement = plan.placement;
      snapshot.metrics = await metrics();
      recordObservation(snapshot.metrics.timestamp, snapshot.metrics.requestRate);
    } catch (decisionError) {
      snapshot.errors.push(decisionError instanceof Error ? decisionError.message : "Capacity service failed");
    }
  }
  snapshot.history = [...history];
  snapshot.events = [...events];
  const latest = provisioner.latest();
  if (`${latest?.id}:${latest?.status}:${latest?.updated_at}` !== proposalVersion) {
    snapshot.proposal = latest;
    snapshot.hosts = provisioner.hosts();
    try {
      const currentVms = latest?.status === "PENDING_APPROVAL" ? latest.vms : [];
      const currentPlan = await evaluatePlan(snapshot.hosts, currentVms);
      snapshot.decision = currentPlan;
      snapshot.placement = currentPlan.placement;
    } catch (error) {
      snapshot.errors.push(error instanceof Error ? error.message : "Capacity refresh failed");
      snapshot.decision = null;
      snapshot.placement = null;
    }
  }
  if (latest) {
    snapshot.decision = latest.decision;
    snapshot.placement = latest.decision.placement;
  }
  return snapshot;
}

export async function evaluatePlan(hosts: Host[], vms: VMRequest[]): Promise<DecisionPlan> {
  return json<DecisionPlan>(`${decisionUrl}/decision`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ hosts, vms }),
  });
}

export { metrics, events };
