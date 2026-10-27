import assert from "node:assert/strict";
import test from "node:test";
import express from "express";
import { api } from "./api.js";

test("HTTP proposal, fallback decision, approval, overload, and failure responses", async () => {
  const nativeFetch = globalThis.fetch;
  let decisionOffline = false;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/decision/live")) return new Response("ML service unavailable", { status: 503 });
    if (url.endsWith("/decision")) {
      if (decisionOffline) return new Response("decision engine offline", { status: 503 });
      const body = JSON.parse(String(init?.body));
      const host = body.hosts[0];
      const vms = body.vms as Array<{ id: string; cpu_required: number; memory_required: number; network_required: number }>;
      const needed = vms.reduce((sum, vm) => sum + vm.cpu_required, 0);
      const feasible = host.allocated_cpu + needed <= host.total_cpu * 0.8;
      const placement = { feasible, placements: feasible ? vms.map(vm => ({ vm_id: vm.id, host_id: host.id,
        increment: { cpu: vm.cpu_required, memory: vm.memory_required, network: vm.network_required } })) : [],
        unplaced: feasible ? [] : vms.map(vm => vm.id), hosts: [] };
      return Response.json({ decision: feasible ? (vms.length ? "RECOMMEND" : "HOLD") : "OVERLOAD",
        reason: feasible ? "Fits" : "No capacity", feasible, placement, requested_increment: { cpu: needed, memory: 0, network: 0 } });
    }
    if (url.includes("localhost:9090")) return Response.json({ data: { result: [] } });
    return nativeFetch(input, init);
  };
  const app = express();
  app.use(express.json());
  app.use("/api", api);
  const server = app.listen(0);
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const base = `http://127.0.0.1:${address.port}/api`;
  const post = (path: string, body: object) => nativeFetch(`${base}${path}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  try {
    assert.equal((await post("/proposals", { vms: [] })).status, 422);
    const created = await post("/proposals", { vms: [{ id: "vm-normal", cpu_required: 2, memory_required: 2, network_required: 100 }] });
    assert.equal(created.status, 201);
    const proposal = await created.json();
    assert.equal(proposal.status, "PENDING_APPROVAL");
    const before = await (await nativeFetch(`${base}/state`)).json();
    assert.equal(before.decision.decision, "RECOMMEND");
    assert.ok(before.errors.length > 0, "prediction failure is visible while capacity remains available");
    const approved = await (await post(`/proposals/${proposal.id}/approve`, {})).json();
    assert.equal(approved.status, "SUCCEEDED");
    assert.equal(approved.verification.passed, true);
    const infrastructure = await (await nativeFetch(`${base}/infrastructure`)).json();
    assert.equal(infrastructure.hosts[0].allocated_cpu, 4);
    assert.equal(infrastructure.vms[0].id, "vm-normal");
    assert.equal((await post("/proposals", { vms: [{ id: "vm-normal", cpu_required: 1, memory_required: 2, network_required: 100 }] })).status, 409);
    const after = await (await nativeFetch(`${base}/state`)).json();
    assert.equal(after.proposal.status, "SUCCEEDED");
    assert.equal(after.decision.decision, "RECOMMEND", "the latest proposal decision remains visible after execution");
    const overload = await (await post("/proposals", { vms: [{ id: "vm-over", cpu_required: 100, memory_required: 2, network_required: 100 }] })).json();
    assert.equal(overload.status, "REJECTED");
    const overloadState = await (await nativeFetch(`${base}/state`)).json();
    assert.equal(overloadState.decision.decision, "OVERLOAD");
    assert.equal(overloadState.placement.feasible, false);
    assert.equal((await post(`/proposals/${overload.id}/approve`, {})).status, 409);
    const failing = await (await post("/proposals", { vms: [{ id: "vm-fail", cpu_required: 1, memory_required: 2, network_required: 100 }] })).json();
    const failed = await (await post(`/proposals/${failing.id}/approve`, { simulate_failure: true })).json();
    assert.equal(failed.status, "FAILED");
    assert.equal(failed.verification.passed, false);
    assert.equal((await (await nativeFetch(`${base}/infrastructure`)).json()).hosts[0].allocated_cpu, 4);
    decisionOffline = true;
    assert.equal((await post("/proposals", { vms: [{ id: "vm-service", cpu_required: 1, memory_required: 2, network_required: 100 }] })).status, 503);
  } finally {
    globalThis.fetch = nativeFetch;
    server.close();
  }
});
