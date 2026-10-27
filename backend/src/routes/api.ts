import { Router } from "express";
import { addEvent, clearDemoHistory, evaluatePlan, getSnapshot, metrics, events } from "../services/orchestration.js";
import { provisioner } from "../services/provisioning.js";
import type { VMRequest } from "../services/provisioning.js";
import { DemoServiceError, demoStatus, resetWorkloadDemo, startDemo, stopDemo } from "../services/demo.js";
import type { DemoScenario } from "../services/demo.js";

export const api = Router();
api.get("/health", (_request, response) => response.json({ status: "healthy", service: "backend" }));
api.get("/metrics", async (_request, response) => response.json(await metrics()));
api.get("/infrastructure", (_request, response) => response.json({ hosts: provisioner.hosts(), vms: provisioner.vms() }));
api.get("/state", async (_request, response) => response.json(await getSnapshot()));
api.get("/prediction", async (_request, response) => response.json((await getSnapshot()).prediction));
api.get("/decision", async (_request, response) => response.json((await getSnapshot()).decision));
api.get("/placement", async (_request, response) => response.json((await getSnapshot()).placement));
api.get("/explanation", async (_request, response) => response.json((await getSnapshot()).explanation));
api.get("/events", (_request, response) => response.json(events));

function demoFailure(response: import("express").Response, error: unknown) {
  const status = error instanceof DemoServiceError ? error.status : 503;
  response.status(status).json({ error: error instanceof Error ? error.message : "Demo service unavailable" });
}

api.get("/demo/status", async (_request, response) => {
  try { response.json(await demoStatus()); }
  catch (error) { demoFailure(response, error); }
});

api.post("/demo/start", async (request, response) => {
  const scenario = request.body?.scenario;
  if (scenario !== "walkthrough" && scenario !== "normal" && scenario !== "high") {
    response.status(422).json({ error: "Choose walkthrough, normal, or high workload" });
    return;
  }
  try {
    const status = await startDemo(scenario as DemoScenario);
    addEvent("DEMO", `Workload ${status.state.toLowerCase()}: ${scenario}`);
    response.json(status);
  } catch (error) { demoFailure(response, error); }
});

api.post("/demo/stop", async (_request, response) => {
  try {
    const status = await stopDemo();
    addEvent("DEMO", `Workload ${status.state.toLowerCase()}`);
    response.json(status);
  } catch (error) { demoFailure(response, error); }
});

api.post("/demo/reset", async (_request, response) => {
  try {
    const status = await demoStatus();
    if (status.state === "RUNNING" || status.state === "STOPPING") {
      response.status(409).json({ error: "Stop the workload before resetting simulated state" });
      return;
    }
    await resetWorkloadDemo();
    provisioner.reset();
    clearDemoHistory();
    addEvent("DEMO_RESET", "Simulated inventory and demo status reset; Prometheus history remains real");
    response.json({ status: "RESET", demo: await demoStatus(), hosts: provisioner.hosts() });
  } catch (error) { demoFailure(response, error); }
});

function validVms(value: unknown): value is VMRequest[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  const ids = new Set<string>();
  return value.every(vm => {
    if (!vm || typeof vm !== "object" || typeof vm.id !== "string" || !vm.id.trim() || ids.has(vm.id)) return false;
    ids.add(vm.id);
    const required = [vm.cpu_required, vm.memory_required, vm.network_required];
    const current = [vm.current_cpu ?? 0, vm.current_memory ?? 0, vm.current_network ?? 0];
    return required.every((item, index) => typeof item === "number" && Number.isFinite(item) && item >= 0
      && typeof current[index] === "number" && Number.isFinite(current[index])
      && current[index] >= 0 && current[index] <= item)
      && vm.host_id === undefined && current.every(item => item === 0)
      && required.some(item => item > 0);
  });
}

api.post("/proposals", async (request, response) => {
  if (!validVms(request.body?.vms)) {
    response.status(422).json({ error: "Provide unique new VMs with finite, non-negative requirements and at least one positive resource" });
    return;
  }
  try {
    const proposal = await provisioner.propose(request.body.vms, evaluatePlan);
    addEvent("PROPOSAL", `${proposal.status}: ${proposal.reason}`, { proposal_id: proposal.id });
    response.status(201).json(proposal);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Capacity service unavailable";
    response.status(message.includes("already provisioned") ? 409 : 503).json({ error: message });
  }
});

api.post("/proposals/:id/approve", async (request, response) => {
  const id = Number(request.params.id);
  if (!Number.isSafeInteger(id) || id < 1 || (request.body?.simulate_failure !== undefined && typeof request.body.simulate_failure !== "boolean")) {
    response.status(422).json({ error: "Invalid proposal ID or simulate_failure flag" });
    return;
  }
  try {
    const proposal = await provisioner.approve(id, evaluatePlan, request.body?.simulate_failure === true);
    addEvent("PROVISIONING", `${proposal.status}: ${proposal.reason}`, { proposal_id: id, verification: proposal.verification });
    response.json(proposal);
  } catch (error) {
    response.status(409).json({ error: error instanceof Error ? error.message : "Approval conflict" });
  }
});

api.post("/proposals/:id/reject", (request, response) => {
  const id = Number(request.params.id);
  if (!Number.isSafeInteger(id) || id < 1) {
    response.status(422).json({ error: "Invalid proposal ID" });
    return;
  }
  try {
    const proposal = provisioner.decline(id);
    addEvent("PROPOSAL", proposal.reason, { proposal_id: id });
    response.json(proposal);
  } catch (error) {
    response.status(409).json({ error: error instanceof Error ? error.message : "Rejection conflict" });
  }
});
