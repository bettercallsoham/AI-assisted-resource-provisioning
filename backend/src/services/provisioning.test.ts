import assert from "node:assert/strict";
import test from "node:test";
import { SimulatedProvisioner } from "./provisioning.js";
import type { Decide, VMRequest } from "./provisioning.js";

const vm = (cpu: number, id = "vm-1"): VMRequest => ({ id, cpu_required: cpu, memory_required: 2, network_required: 100 });
const initial = [{ id: "h1", total_cpu: 8, total_memory: 16, total_network: 1000,
                   allocated_cpu: 1, allocated_memory: 2, allocated_network: 100 }];
const decide: Decide = async (hosts, vms) => {
  const host = hosts[0];
  const increment = { cpu: vms.reduce((sum, item) => sum + item.cpu_required, 0),
                      memory: vms.reduce((sum, item) => sum + item.memory_required, 0),
                      network: vms.reduce((sum, item) => sum + item.network_required, 0) };
  const feasible = host.allocated_cpu + increment.cpu <= host.total_cpu * 0.8
    && host.allocated_memory + increment.memory <= host.total_memory * 0.8
    && host.allocated_network + increment.network <= host.total_network * 0.8;
  return { decision: feasible ? "RECOMMEND" : "OVERLOAD", reason: feasible ? "Fits" : "No capacity",
           feasible, placement: { feasible, placements: feasible ? vms.map(item => ({ vm_id: item.id, host_id: host.id,
             increment: { cpu: item.cpu_required, memory: item.memory_required, network: item.network_required } })) : [],
             unplaced: feasible ? [] : vms.map(item => item.id) } };
};

test("approval commits a feasible plan and verifies the inventory", async () => {
  const service = new SimulatedProvisioner(initial);
  const proposal = await service.propose([vm(2)], decide);
  assert.equal(proposal.status, "PENDING_APPROVAL");
  assert.equal(service.hosts()[0].allocated_cpu, 1);
  const result = await service.approve(proposal.id, decide);
  assert.equal(result.status, "SUCCEEDED");
  assert.equal(result.verification?.passed, true);
  assert.equal(service.hosts()[0].allocated_cpu, 3);
  assert.equal(service.hosts()[0].allocated_memory, 4);
  assert.equal(service.hosts()[0].allocated_network, 200);
  assert.deepEqual(service.vms(), [{ id: "vm-1", host_id: "h1", cpu: 2, memory: 2, network: 100 }]);
  await assert.rejects(service.propose([vm(2)], decide), /already provisioned/);
});

test("overload is rejected and cannot be approved", async () => {
  const service = new SimulatedProvisioner(initial);
  const proposal = await service.propose([vm(20)], decide);
  assert.equal(proposal.status, "REJECTED");
  await assert.rejects(service.approve(proposal.id, decide));
  assert.deepEqual(service.hosts(), initial);
  assert.deepEqual(service.vms(), []);
});

test("simulated adapter failure leaves inventory unchanged", async () => {
  const service = new SimulatedProvisioner(initial);
  const proposal = await service.propose([vm(2)], decide);
  const result = await service.approve(proposal.id, decide, true);
  assert.equal(result.status, "FAILED");
  assert.equal(result.verification?.passed, false);
  assert.deepEqual(service.hosts(), initial);
});

test("capacity is rechecked at approval and an obsolete plan is rejected", async () => {
  const service = new SimulatedProvisioner(initial);
  const first = await service.propose([vm(4, "first")], decide);
  const second = await service.propose([vm(4, "second")], decide);
  assert.equal((await service.approve(first.id, decide)).status, "SUCCEEDED");
  assert.equal((await service.approve(second.id, decide)).status, "REJECTED");
  assert.equal(service.hosts()[0].allocated_cpu, 5);
});

test("operator decline and service failure do not allocate resources", async () => {
  const service = new SimulatedProvisioner(initial);
  const proposal = await service.propose([vm(2)], decide);
  assert.equal(service.decline(proposal.id).status, "DECLINED");
  await assert.rejects(service.approve(proposal.id, decide));
  await assert.rejects(service.propose([vm(2)], async () => { throw new Error("decision engine offline"); }));
  assert.deepEqual(service.hosts(), initial);
});
