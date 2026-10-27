import { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, LinearProgress, Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const api = import.meta.env.VITE_API_URL ?? "http://localhost:3000/api";

type Metrics = { requestRate: number | null; cpu: number | null; memory: number | null; network: number | null; latency: number | null; timestamp: string };
type Host = { id: string; total_cpu: number; total_memory: number; total_network: number; allocated_cpu: number; allocated_memory: number; allocated_network: number };
type Placement = { feasible: boolean; placements: Array<{ vm_id: string; host_id: string; increment: Record<string, number> }>; unplaced: string[] };
type Proposal = { id: number; status: string; reason: string; decision: { decision: string; placement: Placement }; verification: { passed: boolean; message: string; hosts: Host[] } | null };
type Feature = { name: string; value: number; contribution: number; direction: string };
type Explanation = { prediction: number; features: Feature[]; ranked_importance: Array<{ name: string; importance: number }> };
type Snapshot = {
  metrics: Metrics; prediction: { predicted_request_rate: number; model: string; origin_timestamp: string; target_timestamp: string } | null;
  resources: { predicted_cpu: number; predicted_memory: number; predicted_network: number } | null;
  decision: { decision?: string; reason?: string; bottleneck?: string; safe_available_capacity?: Record<string, number>; requested_increment?: Record<string, number>; units?: Record<string, string> } | null;
  placement: Placement | null; proposal: Proposal | null; hosts: Host[];
  explanation: Record<string, Explanation> | null;
  history: Array<{ timestamp: string; actual: number | null; predicted: number | null }>;
  errors: string[]; events: Array<{ timestamp: string; event_type: string; message: string }>;
};
type DemoStatus = { state: string; scenario: string | null; phase: string | null; started_at: string | null; ended_at: string | null; requests: number; successful: number; failed: number; error: string | null };

const empty: Snapshot = {
  metrics: { requestRate: null, cpu: null, memory: null, network: null, latency: null, timestamp: "" },
  prediction: null, resources: null, decision: null, placement: null, proposal: null,
  hosts: [], explanation: null, history: [], errors: [], events: [],
};
const label = (value: string) => value.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, character => character.toUpperCase());
const show = (value: number | null | undefined, digits = 1) => value === null || value === undefined || !Number.isFinite(value)
  ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const time = (value: string | null) => value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";

async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`${api}${path}`, body === undefined ? undefined : {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  const payload = await response.json() as T & { error?: string };
  if (!response.ok) throw new Error(payload.error ?? `${path} returned ${response.status}`);
  return payload;
}

function MetricCard({ title, value, unit, detail }: { title: string; value: number | null; unit: string; detail: string }) {
  return <Paper className="metric-card"><span className="overline">{title}</span><strong>{show(value)} <small>{unit}</small></strong><span className="microcopy">{detail}</span></Paper>;
}

function HostCard({ host }: { host: Host }) {
  const rows: Array<[string, number, number, string]> = [
    ["CPU", host.allocated_cpu, host.total_cpu, "vCPU"],
    ["Memory", host.allocated_memory, host.total_memory, "GiB"],
    ["Network", host.allocated_network, host.total_network, "B/s"],
  ];
  return <div className="host-card"><div className="host-heading"><strong>{host.id}</strong><span>Committed allocation</span></div>{rows.map(([name, used, total, unit]) => <div className="host-resource" key={name}><div><span>{name}</span><b>{show(used)} / {show(total)} {unit}</b></div><LinearProgress variant="determinate" value={Math.min(100, used / total * 100)} /></div>)}<small>Decisions use an 80% per-host safety limit.</small></div>;
}

function ExplainPanel({ resource, explanation }: { resource: string; explanation?: Explanation }) {
  return <details className="explain-panel"><summary><span>{label(resource)} prediction</span><strong>{explanation ? show(explanation.prediction) : "Waiting"}</strong></summary>{explanation ? <div className="explain-content"><p>Tree-path contributions for this RF output; they do not prove causal demand.</p>{explanation.features.map(feature => <div className="explain-row" key={feature.name}><span>{label(feature.name)}</span><b className={feature.direction}>{feature.contribution >= 0 ? "+" : ""}{show(feature.contribution, 2)}</b></div>)}</div> : <p className="muted">Explanation appears after a successful live prediction.</p>}</details>;
}

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot>(empty);
  const [demo, setDemo] = useState<DemoStatus | null>(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [demoError, setDemoError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    let snapshotBusy = false;
    let demoBusy = false;
    const pollSnapshot = async () => {
      if (snapshotBusy) return;
      snapshotBusy = true;
      try {
        const next = await request<Snapshot>("/state");
        if (active) { setSnapshot(next); setBackendOnline(true); }
      } catch (error) {
        if (active) { setBackendOnline(false); setSnapshot(previous => ({ ...previous, errors: [error instanceof Error ? error.message : "Backend unavailable"] })); }
      } finally { snapshotBusy = false; }
    };
    const pollDemo = async () => {
      if (demoBusy) return;
      demoBusy = true;
      try {
        const next = await request<DemoStatus>("/demo/status");
        if (active) { setDemo(next); setDemoError(""); }
      } catch (error) {
        if (active) setDemoError(error instanceof Error ? error.message : "Workload control unavailable");
      } finally { demoBusy = false; }
    };
    void pollSnapshot();
    void pollDemo();
    const snapshotTimer = window.setInterval(pollSnapshot, 5000);
    const demoTimer = window.setInterval(pollDemo, 2000);
    return () => { active = false; window.clearInterval(snapshotTimer); window.clearInterval(demoTimer); };
  }, []);

  async function demoAction(path: string, body: object = {}) {
    setBusy(true); setActionError("");
    try {
      if (path === "/demo/reset") {
        const result = await request<{ demo: DemoStatus; hosts: Host[] }>(path, body);
        setDemo(result.demo);
        setSnapshot(previous => ({ ...previous, hosts: result.hosts, proposal: null, decision: null,
          placement: null, history: [], events: [] }));
      } else {
        setDemo(await request<DemoStatus>(path, body));
      }
      setDemoError("");
    } catch (error) { setActionError(error instanceof Error ? error.message : "Demo action failed"); }
    finally { setBusy(false); }
  }

  async function proposalAction(path: string, body: object) {
    setBusy(true); setActionError("");
    try {
      const proposal = await request<Proposal>(path, body);
      setSnapshot(previous => ({ ...previous, proposal, decision: proposal.decision,
        placement: proposal.decision.placement, hosts: proposal.verification?.hosts ?? previous.hosts }));
    } catch (error) { setActionError(error instanceof Error ? error.message : "Proposal action failed"); }
    finally { setBusy(false); }
  }

  function propose(overload: boolean) {
    const id = `${overload ? "overload" : "demo"}-vm-${Date.now()}`;
    void proposalAction("/proposals", { vms: [{ id, cpu_required: overload ? 100 : 2,
      memory_required: overload ? 100 : 4, network_required: overload ? 100_000_000 : 100_000 }] });
  }

  const running = demo?.state === "RUNNING" || demo?.state === "STOPPING";
  const decision = snapshot.decision?.decision ?? "WAITING";
  const proposal = snapshot.proposal;
  const observed = snapshot.metrics;
  const chartData = snapshot.history.map(point => ({ ...point, epoch: Date.parse(point.timestamp) }));
  const capacityRows: Array<[string, string, number | undefined, number | undefined, string]> = [
    ["CPU", "cpu", snapshot.resources?.predicted_cpu, observed.cpu ?? undefined, "%"],
    ["Memory", "memory", snapshot.resources?.predicted_memory, observed.memory ?? undefined, "%"],
    ["Network", "network", snapshot.resources?.predicted_network, observed.network ?? undefined, "B/s"],
  ];

  return <div className="app-shell">
    <header className="topbar"><div className="brand-mark">RP</div><div className="brand-copy"><span>RESOURCE PROVISIONING</span><strong>Operations Console</strong></div><div className="topbar-right"><span className={`connection ${backendOnline ? snapshot.errors.length ? "partial" : "online" : "offline"}`} />{!backendOnline ? "Backend offline" : snapshot.errors.length ? "Partial service" : "Live services"}</div></header>
    <main>
      <section className="hero"><div><span className="overline">ON-PREMISES INFRASTRUCTURE / DEMONSTRATION</span><h1>From live workload to a safe allocation decision.</h1><p>Observe service metrics, review model indicators, and approve a capacity-checked action against simulated hosts.</p></div><div className="hero-status"><span className="overline">CURRENT CAPACITY DECISION</span><strong className={`decision-badge ${decision.toLowerCase()}`}>{label(decision)}</strong><small>{snapshot.decision?.reason ?? "Waiting for a capacity response"}</small></div></section>

      {!backendOnline && <Alert severity="error" className="service-alert">Backend unavailable. Start the Compose stack from the README, then check <code>http://localhost:3000/api/health</code>.</Alert>}
      {snapshot.errors.length > 0 && backendOnline && <Alert severity="warning" className="service-alert">Live path is partial: {snapshot.errors.join(" | ")}. Capacity checks remain available when the decision engine responds.</Alert>}
      {demoError && <Alert severity="warning" className="service-alert">Demo controls unavailable: {demoError}. Start or rebuild the workload service.</Alert>}

      <section className="panel demo-panel"><div className="section-heading"><div><span className="overline">01 / CONTROL</span><h2>Demo Mode</h2><p>Bounded traffic presets send real HTTP requests to the workload service. Monitoring remains available without Demo Mode.</p></div><Chip label={demo ? label(demo.state) : "Connecting"} className={`demo-chip ${(demo?.state ?? "idle").toLowerCase()}`} /></div><div className="demo-actions"><Button variant="contained" disabled={busy || running || !!demoError} onClick={() => void demoAction("/demo/start", { scenario: "walkthrough" })}>Start Demo</Button><Button variant="outlined" disabled={busy || running || !!demoError} onClick={() => void demoAction("/demo/start", { scenario: "normal" })}>Run Normal Workload</Button><Button variant="outlined" disabled={busy || running || !!demoError} onClick={() => void demoAction("/demo/start", { scenario: "high" })}>Run High-Load</Button><Button color="warning" variant="outlined" disabled={busy || !running || !!demoError} onClick={() => void demoAction("/demo/stop")}>Stop Demo</Button><Button variant="text" disabled={busy || running || !!demoError} onClick={() => void demoAction("/demo/reset")}>Reset Simulated State</Button></div><div className="demo-readout"><span>Scenario <strong>{demo?.scenario ? label(demo.scenario) : "None"}</strong></span><span>Phase <strong>{demo?.phase ? label(demo.phase) : "—"}</strong></span><span>Successful requests <strong>{show(demo?.successful)}</strong></span><span>Failed requests <strong>{show(demo?.failed)}</strong></span></div>{demo?.error && <Alert severity="error">Workload scenario failed: {demo.error}</Alert>}<small className="disclaimer">Reset clears only the backend's simulated VM allocations and demo status. It does not erase Prometheus measurements or source datasets.</small></section>

      <div className="section-heading section-break"><div><span className="overline">02 / OBSERVE</span><h2>Current measurements</h2><p>From the running workload and Prometheus. Last update: {time(observed.timestamp || null)}.</p></div><span className="section-tag">CURRENT</span></div>
      <section className="metrics-grid"><MetricCard title="Request rate" value={observed.requestRate} unit="req/s" detail="30-second rolling rate" /><MetricCard title="CPU utilization" value={observed.cpu} unit="%" detail="Workload service" /><MetricCard title="Memory utilization" value={observed.memory} unit="%" detail="Workload service" /><MetricCard title="Network throughput" value={observed.network} unit="B/s" detail="Workload service" /><MetricCard title="Request latency" value={observed.latency} unit="ms" detail="30-second weighted mean" /></section>

      <section className="main-grid"><Paper className="panel trend-panel"><div className="section-heading"><div><span className="overline">03 / FORECAST</span><h2>Workload over time</h2><p>Current rate and next-step forecast are aligned to the same five-second timeline.</p></div><Chip label={snapshot.prediction?.model?.toUpperCase() ?? "Waiting for forecast"} /></div>{chartData.length ? <ResponsiveContainer width="100%" height={260}><ComposedChart data={chartData}><CartesianGrid stroke="#29414c" strokeDasharray="3 5"/><XAxis dataKey="epoch" type="number" scale="time" domain={["dataMin", "dataMax"]} stroke="#92a7af" tickLine={false} tickFormatter={value => time(new Date(value).toISOString())}/><YAxis stroke="#92a7af" tickLine={false}/><Tooltip labelFormatter={value => time(new Date(Number(value)).toISOString())} contentStyle={{ background: "#172631", border: "1px solid #38515c", borderRadius: 10 }}/><Line name="Current request rate" type="linear" dataKey="actual" stroke="#53d8ce" strokeWidth={2} dot={false} connectNulls={false}/><Line name="Forecast request rate" type="linear" dataKey="predicted" stroke="#f3b877" strokeWidth={2} dot={false} connectNulls={true}/></ComposedChart></ResponsiveContainer> : <div className="empty-chart">{backendOnline ? "Waiting for request-rate samples. Start a workload to populate the chart." : "Connect the backend to view workload history."}</div>}<div className="forecast-strip"><span>Latest forecast for {time(snapshot.prediction?.target_timestamp ?? null)}</span><strong>{show(snapshot.prediction?.predicted_request_rate)} <small>req/s</small></strong></div></Paper>
      <Paper className="panel model-panel"><div className="section-heading"><div><span className="overline">MODEL OUTPUT / INFORMATIONAL</span><h2>Resource indicators</h2><p>Predictions are not VM allocations and have not been validated on this live workload.</p></div></div><Table size="small"><TableHead><TableRow><TableCell>Resource</TableCell><TableCell align="right">Observed</TableCell><TableCell align="right">Next-step RF</TableCell></TableRow></TableHead><TableBody>{capacityRows.map(([name, , predicted, actual, unit]) => <TableRow key={name}><TableCell>{name}</TableCell><TableCell align="right">{show(actual)} {unit}</TableCell><TableCell align="right">{show(predicted)} {unit}</TableCell></TableRow>)}</TableBody></Table><p className="disclaimer">The saved RF artifacts did not beat a trailing-mean baseline in Phase 3. VM requests below use explicit vCPU, GiB, and B/s requirements.</p></Paper></section>

      <div className="section-heading section-break"><div><span className="overline">04 / DECIDE</span><h2>Capacity and placement</h2><p>Decision engine checks the complete proposal against per-host safe limits before presenting it.</p></div><span className="section-tag">SIMULATED HOSTS</span></div>
      <section className="main-grid"><Paper className={`panel decision-panel ${decision.toLowerCase()}`}><span className="overline">CAPACITY DECISION</span><strong className="decision-word">{label(decision)}</strong><p>{snapshot.decision?.reason ?? "No capacity decision yet. Check the decision-engine service."}</p><div className="capacity-grid">{(["cpu", "memory", "network"] as const).map(resource => <div key={resource}><span>{label(resource)} increment</span><strong>{show(snapshot.decision?.requested_increment?.[resource])} {snapshot.decision?.units?.[resource] ?? ""}</strong><small>Safe headroom {show(snapshot.decision?.safe_available_capacity?.[resource])} {snapshot.decision?.units?.[resource] ?? ""}</small></div>)}</div></Paper><Paper className="panel placement-panel"><span className="overline">PROPOSED PLACEMENT</span><h2>{snapshot.placement?.placements?.length ? `${snapshot.placement.placements.length} feasible assignment` : snapshot.placement?.feasible ? "No allocation requested" : "No feasible placement"}</h2>{snapshot.placement?.placements?.length ? snapshot.placement.placements.map(item => <div className="placement-item" key={item.vm_id}><div><strong>{item.vm_id}</strong><small>Requested increment</small></div><span>→</span><div><strong>{item.host_id}</strong><small>{show(item.increment.cpu)} vCPU · {show(item.increment.memory)} GiB · {show(item.increment.network)} B/s</small></div></div>) : <p className="muted">{snapshot.placement?.feasible ? "Create a proposal to see its placement." : "Unsafe plans are rejected as a whole and cannot be executed."}</p>}{!!snapshot.placement?.unplaced?.length && <Alert severity="error">Unplaced VM: {snapshot.placement.unplaced.join(", ")}</Alert>}</Paper></section>

      <section className="panel provisioning-panel"><div className="section-heading"><div><span className="overline">05 / APPROVE AND VERIFY</span><h2>Simulated provisioning</h2><p>Operator approval is required. Only the in-memory simulated inventory changes; no real VM is created.</p></div><Chip label={proposal ? label(proposal.status) : "No proposal"} className={`proposal-chip ${(proposal?.status ?? "idle").toLowerCase()}`} /></div><div className="provision-actions"><Button variant="contained" disabled={busy || !backendOnline} onClick={() => propose(false)}>Propose 2 vCPU / 4 GiB VM</Button><Button variant="outlined" color="error" disabled={busy || !backendOnline} onClick={() => propose(true)}>Try Unsafe Allocation</Button>{proposal?.status === "PENDING_APPROVAL" && <><Button variant="contained" color="success" disabled={busy} onClick={() => void proposalAction(`/proposals/${proposal.id}/approve`, {})}>Approve &amp; Simulate</Button><Button variant="outlined" disabled={busy} onClick={() => void proposalAction(`/proposals/${proposal.id}/reject`, {})}>Reject Proposal</Button><Button variant="text" color="warning" disabled={busy} onClick={() => void proposalAction(`/proposals/${proposal.id}/approve`, { simulate_failure: true })}>Test Execution Failure</Button></>}</div>{actionError && <Alert severity="error">{actionError}</Alert>}{proposal ? <div className={`proposal-result ${proposal.status.toLowerCase()}`}><span className="overline">PROPOSAL #{proposal.id}</span><strong>{label(proposal.status)}</strong><p>{proposal.reason}</p><small>Decision: {proposal.decision.decision} · Planned host: {proposal.decision.placement.placements?.map(item => item.host_id).join(", ") || "none"}</small>{proposal.verification && <Alert severity={proposal.verification.passed ? "success" : "error"}>{proposal.verification.message}</Alert>}</div> : <div className="empty-inline">No proposal yet. Submit a safe or unsafe VM request to start the review.</div>}<p className="disclaimer">High traffic does not automatically request more VM resources. The unsafe allocation button submits an explicit demo-only request to exercise rejection.</p></section>

      <div className="section-heading section-break"><div><span className="overline">06 / VERIFY</span><h2>Simulated infrastructure</h2><p>These bars reflect committed allocations, not pending recommendations.</p></div></div>
      <section className="hosts-grid">{snapshot.hosts.length ? snapshot.hosts.map(host => <HostCard key={host.id} host={host} />) : <Paper className="panel empty-inline">Host inventory unavailable. Check the backend and decision engine.</Paper>}</section>

      <section className="bottom-grid"><Paper className="panel"><div className="section-heading"><div><span className="overline">MODEL CONTEXT</span><h2>RF explanations</h2><p>Expand a resource to inspect feature contributions.</p></div></div>{["cpu", "memory", "network"].map(resource => <ExplainPanel key={resource} resource={resource} explanation={snapshot.explanation?.[resource]} />)}</Paper><Paper className="panel"><div className="section-heading"><div><span className="overline">SYSTEM ACTIVITY</span><h2>Event trail</h2><p>Current backend process · last 20 events</p></div></div>{snapshot.events.length ? snapshot.events.slice(0, 10).map((event, index) => <div className="event-row" key={`${event.timestamp}-${event.event_type}-${index}`}><time>{time(event.timestamp)}</time><div><strong>{label(event.event_type)}</strong><span>{event.message}</span></div></div>) : <div className="empty-inline">Events will appear as monitoring and decisions run.</div>}</Paper></section>
      <footer><span>Workload telemetry · unvalidated model indicators · capacity-checked simulated actions</span><span>Refreshes every 5 seconds</span></footer>
    </main>
    {busy && <Box className="busy-indicator"><CircularProgress size={16} /> Processing action…</Box>}
  </div>;
}
