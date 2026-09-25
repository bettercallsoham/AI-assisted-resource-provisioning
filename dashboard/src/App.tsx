import { useEffect, useState } from "react";
import { Alert, Box, Chip, LinearProgress, Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const api = import.meta.env.VITE_API_URL ?? "http://localhost:3000/api";
type Metrics = { requestRate: number | null; cpu: number | null; memory: number | null; network: number | null; latency: number | null; timestamp: string };
type ResourcePrediction = { predicted_cpu: number; predicted_memory: number; predicted_network: number };
type Feature = { name: string; value: number; contribution: number; direction: string };
type Explanation = { prediction: number; base_value: number; features: Feature[]; ranked_importance: Array<{ name: string; importance: number }> };
type Host = { id: string; total_cpu: number; total_memory: number; total_network: number; allocated_cpu: number; allocated_memory: number; allocated_network: number };
type Placement = { placements?: Array<{ vm_id: string; host_id: string }>; unplaced?: string[]; hosts?: Array<{ id: string; remaining: Record<string, number> }> };
type State = { metrics: Metrics; prediction: { predicted_request_rate: number; model: string } | null; resources: ResourcePrediction | null; decision: { decision?: string; bottleneck?: string; reason?: string; predicted_demand?: Record<string, number>; available_capacity?: Record<string, number> } | null; placement: Placement | null; explanation: Record<string, Explanation> | null; hosts: Host[]; history: Array<{ timestamp: string; actual: number; predicted: number }>; errors: string[]; events: Array<{ timestamp: string; event_type: string; message: string }> };
const empty: State = { metrics: { requestRate: null, cpu: null, memory: null, network: null, latency: null, timestamp: "" }, prediction: null, resources: null, decision: null, placement: null, explanation: null, hosts: [], history: [], errors: [], events: [] };
const show = (number: number | null | undefined, digits = 1) => number === null || number === undefined || !Number.isFinite(number) ? "-" : number.toLocaleString(undefined, { maximumFractionDigits: digits });
const readable = (name: string) => name.replace(/_/g, " ");
const statusLabel = (decision: string) => readable(decision);

function MetricCard({ title, metric, unit, tone }: { title: string; metric: number | null; unit: string; tone: string }) {
  return <Paper className={`metric ${tone}`}><Typography className="label">{title}</Typography><Typography className="metric-value">{show(metric)} <small>{unit}</small></Typography><span className="pulse" /></Paper>;
}

function ExplanationPanel({ resource, explanation }: { resource: string; explanation?: Explanation }) {
  if (!explanation) return <Paper className="panel"><Typography className="kicker">SHAP / {resource}</Typography><Typography className="muted">Waiting for the live explanation.</Typography></Paper>;
  const largest = Math.max(...explanation.features.map(feature => Math.abs(feature.contribution)), 1);
  return <Paper className="panel shap-panel"><div className="panel-heading"><div><Typography className="kicker">SHAP / {resource}</Typography><Typography variant="h2">Why this prediction?</Typography></div><Chip label={show(explanation.prediction)} /></div><div className="shap-list">{explanation.features.map(feature => <div className="shap-row" key={feature.name}><div className="shap-name"><span>{readable(feature.name)}</span><small>input {show(feature.value, 2)}</small></div><div className={`shap-track ${feature.direction}`}><i style={{ width: `${Math.min(Math.abs(feature.contribution) / largest * 100, 100)}%` }} /></div><b className={feature.direction}>{feature.contribution >= 0 ? "+" : ""}{show(feature.contribution, 2)}</b></div>)}</div><div className="ranked">{explanation.ranked_importance.slice(0, 3).map((item, index) => <span key={item.name}><em>0{index + 1}</em>{readable(item.name)}</span>)}</div></Paper>;
}

export default function App() {
  const [state, setState] = useState<State>(empty);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch(`${api}/state`);
        if (!response.ok) throw new Error(`Live API returned ${response.status}`);
        const next = await response.json() as State;
        if (active) { setState(next); setConnected(true); }
      } catch (error) {
        if (active) { setConnected(false); setState(previous => ({ ...previous, errors: [error instanceof Error ? error.message : "Live API unavailable"] })); }
      }
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const decision = state.decision?.decision ?? "WAITING";
  const placementHosts = state.placement?.hosts ?? [];
  const chartData = state.history.map(point => ({ ...point, time: new Date(point.timestamp).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" }) }));
  const capacityRows: Array<[string, number | undefined, number | undefined, string]> = [
    ["CPU", state.resources?.predicted_cpu, state.decision?.available_capacity?.cpu, "%"],
    ["Memory", state.resources?.predicted_memory, state.decision?.available_capacity?.memory, "%"],
    ["Network", state.resources?.predicted_network, state.decision?.available_capacity?.network, "B/s"],
  ];

  return <main>
    <header><div><Typography className="eyebrow">AI RESOURCE PROVISIONING / LIVE CONTROL ROOM</Typography><Typography variant="h1">Provisioning cockpit</Typography><Typography className="subtitle">Prometheus observation -&gt; LSTM forecast -&gt; Random Forest demand -&gt; explainable capacity decision.</Typography></div><div className="header-status"><Chip className={`status ${statusLabel(decision).toLowerCase()}`} label={statusLabel(decision)} /><span className={connected ? "live-dot" : "live-dot offline"}>{connected ? "LIVE / 5 SEC POLL" : "API DISCONNECTED"}</span></div></header>
    {state.errors.length > 0 && <Alert severity="warning" sx={{ mb: 2 }}>{state.errors[0]}</Alert>}
    <section className="metric-grid"><MetricCard title="Current request rate" metric={state.metrics.requestRate} unit="req/s" tone="cyan" /><MetricCard title="CPU utilization" metric={state.metrics.cpu} unit="%" tone="coral" /><MetricCard title="Memory utilization" metric={state.metrics.memory} unit="%" tone="gold" /><MetricCard title="Network throughput" metric={state.metrics.network} unit="B/s" tone="mint" /></section>
    <section className="grid-two"><Paper className="panel chart-panel"><div className="panel-heading"><div><Typography className="kicker">WORKLOAD FORECAST</Typography><Typography variant="h2">Historical vs predicted request rate</Typography></div><Chip label={state.prediction?.model ?? "waiting"} /></div><ResponsiveContainer width="100%" height={300}><AreaChart data={chartData}><defs><linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#36d1dc" stopOpacity={.45}/><stop offset="100%" stopColor="#36d1dc" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="#263342"/><XAxis dataKey="time" stroke="#8391a4"/><YAxis stroke="#8391a4"/><Tooltip contentStyle={{ background: "#17232d", border: "1px solid #35505a" }}/><Legend/><Area name="observed" type="monotone" dataKey="actual" stroke="#36d1dc" fill="url(#actualFill)"/><Area name="LSTM forecast" type="monotone" dataKey="predicted" stroke="#ff8b6a" fill="none" strokeDasharray="6 4"/></AreaChart></ResponsiveContainer></Paper><Paper className="panel decision"><Typography className="kicker">DECISION ENGINE</Typography><Typography className="decision-word">{statusLabel(decision)}</Typography><Typography className="decision-bottle">Bottleneck <strong>{state.decision?.bottleneck ?? "-"}</strong></Typography><Box className="decision-line"><span>REASON</span><p>{state.decision?.reason ?? "Waiting for the live decision path."}</p></Box><Box className="decision-line"><span>LSTM NEXT RATE</span><p>{show(state.prediction?.predicted_request_rate)} req/s</p></Box></Paper></section>
    <section className="grid-two"><Paper className="panel"><Typography className="kicker">RANDOM FOREST / CAPACITY</Typography><Typography variant="h2">Predicted demand</Typography><Table size="small"><TableHead><TableRow><TableCell>Resource</TableCell><TableCell>Predicted</TableCell><TableCell>Available</TableCell><TableCell>Read</TableCell></TableRow></TableHead><TableBody>{capacityRows.map(([name, predicted, available, unit]) => { const pressured = predicted !== undefined && available !== undefined && predicted > available; return <TableRow key={name}><TableCell>{name}</TableCell><TableCell>{show(predicted)} <small>{unit}</small></TableCell><TableCell>{show(available)} <small>{unit}</small></TableCell><TableCell><Chip size="small" label={pressured ? "PRESSURE" : "WITHIN"} className={pressured ? "pressure-chip" : "within-chip"}/></TableCell></TableRow>; })}</TableBody></Table></Paper><Paper className="panel"><Typography className="kicker">INFRASTRUCTURE CAPACITY</Typography><Typography variant="h2">Host utilization</Typography>{state.hosts.length === 0 ? <Typography className="muted">Waiting for host capacity.</Typography> : state.hosts.map(host => { const placed = placementHosts.find(item => item.id === host.id); const remaining = placed?.remaining ?? { cpu: host.total_cpu - host.allocated_cpu, memory: host.total_memory - host.allocated_memory, network: host.total_network - host.allocated_network }; const usedCpu = host.total_cpu - remaining.cpu; const usedMemory = host.total_memory - remaining.memory; return <div className="host-row" key={host.id}><div className="host-title"><b>{host.id}</b><span>{usedCpu.toFixed(1)} / {host.total_cpu} CPU - {usedMemory.toFixed(1)} / {host.total_memory} memory</span></div><LinearProgress variant="determinate" value={Math.min((usedCpu / host.total_cpu) * 100, 100)} /><small>Network {show(host.total_network - remaining.network)} / {show(host.total_network)} B/s</small></div>; })}</Paper></section>
    <section className="placement-strip panel"><div className="panel-heading"><div><Typography className="kicker">BEST-FIT DECREASING</Typography><Typography variant="h2">VM placement</Typography></div><Chip label={`${state.placement?.placements?.length ?? 0} assigned`} /></div><div className="placement-grid">{state.placement?.placements?.map(item => <div className="placement-card" key={item.vm_id}><span>{item.vm_id}</span><b>{item.host_id}</b><small>selected host</small></div>) ?? <Typography className="muted">Waiting for placement response.</Typography>}</div>{(state.placement?.unplaced?.length ?? 0) > 0 && <Alert severity="warning">Unplaced: {state.placement?.unplaced?.join(", ")}</Alert>}</section>
    <section className="shap-grid">{["cpu", "memory", "network"].map(resource => <ExplanationPanel key={resource} resource={resource} explanation={state.explanation?.[resource]} />)}</section>
    <section className="panel timeline"><div className="panel-heading"><div><Typography className="kicker">EVENT TIMELINE</Typography><Typography variant="h2">Live decision trail</Typography></div><span className="muted">{state.metrics.timestamp ? new Date(state.metrics.timestamp).toLocaleTimeString() : "-"}</span></div><div className="events">{state.events.slice(0, 10).map(event => <div className="event" key={`${event.timestamp}-${event.event_type}`}><time>{new Date(event.timestamp).toLocaleTimeString()}</time><span><b>{readable(event.event_type)}</b>{event.message}</span></div>)}</div></section>
    <footer>Real Prometheus metrics - live ML predictions - simulated infrastructure placement - refreshes every 5 seconds</footer>
  </main>;
}