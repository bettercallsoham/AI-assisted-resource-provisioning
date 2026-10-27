import type { Host } from "../types/index.js";

export type ResourceAmounts = { cpu: number; memory: number; network: number };
export type VMRequest = {
  id: string; cpu_required: number; memory_required: number; network_required: number;
  host_id?: string; current_cpu?: number; current_memory?: number; current_network?: number;
};
export type DecisionPlan = {
  decision: string; reason: string; feasible: boolean;
  placement: { feasible: boolean; placements: Array<{ vm_id: string; host_id: string; increment: ResourceAmounts }>; unplaced: string[] };
};
export type ProposalStatus = "PENDING_APPROVAL" | "REJECTED" | "DECLINED" | "EXECUTING" | "SUCCEEDED" | "FAILED";
export type Proposal = {
  id: number; vms: VMRequest[]; status: ProposalStatus; decision: DecisionPlan;
  reason: string; created_at: string; updated_at: string;
  verification: { passed: boolean; message: string; hosts: Host[] } | null;
};
export type SimulatedVM = { id: string; host_id: string; cpu: number; memory: number; network: number };
export type Decide = (hosts: Host[], vms: VMRequest[]) => Promise<DecisionPlan>;

const resources = ["cpu", "memory", "network"] as const;
const safetyThreshold = 0.8;

function copyHosts(hosts: Host[]): Host[] { return hosts.map(host => ({ ...host })); }
function copyVms(vms: VMRequest[]): VMRequest[] { return vms.map(vm => ({ ...vm })); }

export class SimulatedProvisioner {
  private initialHosts: Host[];
  private inventory: Host[];
  private provisionedVms = new Map<string, SimulatedVM>();
  private proposals = new Map<number, Proposal>();
  private nextId = 1;
  private executing = false;

  constructor(initialHosts: Host[]) {
    this.initialHosts = copyHosts(initialHosts);
    this.inventory = copyHosts(initialHosts);
  }

  hosts(): Host[] { return copyHosts(this.inventory); }
  vms(): SimulatedVM[] { return [...this.provisionedVms.values()].map(vm => ({ ...vm })); }
  latest(): Proposal | null { return this.proposals.get(this.nextId - 1) ?? null; }
  get(id: number): Proposal | undefined { return this.proposals.get(id); }

  reset(): void {
    if (this.executing) throw new Error("Wait for simulated execution before resetting");
    this.inventory = copyHosts(this.initialHosts);
    this.provisionedVms.clear();
    this.proposals.clear();
    this.nextId = 1;
  }

  async propose(vms: VMRequest[], decide: Decide): Promise<Proposal> {
    if (this.executing) throw new Error("A simulated execution is in progress");
    if (!Array.isArray(vms) || vms.length === 0) throw new Error("At least one VM request is required");
    if (vms.some(vm => this.provisionedVms.has(vm.id))) throw new Error("A requested VM ID is already provisioned");
    const decision = await decide(this.hosts(), copyVms(vms));
    const accepted = decision.decision === "RECOMMEND" && decision.feasible && decision.placement.feasible;
    const now = new Date().toISOString();
    const proposal: Proposal = {
      id: this.nextId++, vms: copyVms(vms), status: accepted ? "PENDING_APPROVAL" : "REJECTED",
      decision, reason: decision.reason, created_at: now, updated_at: now, verification: null,
    };
    this.proposals.set(proposal.id, proposal);
    return proposal;
  }

  decline(id: number): Proposal {
    const proposal = this.proposals.get(id);
    if (!proposal || proposal.status !== "PENDING_APPROVAL") throw new Error("Proposal is not awaiting approval");
    proposal.status = "DECLINED";
    proposal.reason = "Operator declined simulated provisioning";
    proposal.updated_at = new Date().toISOString();
    return proposal;
  }

  async approve(id: number, decide: Decide, simulateFailure = false): Promise<Proposal> {
    const proposal = this.proposals.get(id);
    if (!proposal || proposal.status !== "PENDING_APPROVAL") throw new Error("Proposal is not awaiting approval");
    if (this.executing) throw new Error("A simulated execution is in progress");
    this.executing = true;
    proposal.status = "EXECUTING";
    proposal.updated_at = new Date().toISOString();
    try {
      const fresh = await decide(this.hosts(), copyVms(proposal.vms));
      if (proposal.vms.some(vm => this.provisionedVms.has(vm.id))) {
        proposal.status = "REJECTED";
        proposal.reason = "A requested VM ID was provisioned after this proposal was created";
        return proposal;
      }
      if (fresh.decision !== "RECOMMEND" || !fresh.feasible || !fresh.placement.feasible) {
        proposal.status = "REJECTED";
        proposal.decision = fresh;
        proposal.reason = `Capacity changed before approval: ${fresh.reason}`;
        return proposal;
      }
      const candidate = copyHosts(this.inventory);
      const seen = new Set<string>();
      for (const assignment of fresh.placement.placements) {
        const vm = proposal.vms.find(item => item.id === assignment.vm_id);
        const host = candidate.find(item => item.id === assignment.host_id);
        if (!vm || !host || seen.has(vm.id) || (vm.host_id && vm.host_id !== host.id)) {
          throw new Error("Placement contains an unknown, repeated, or wrongly pinned VM/host");
        }
        seen.add(vm.id);
        for (const resource of resources) {
          const increment = assignment.increment[resource];
          const expected = vm[`${resource}_required`] - (vm[`current_${resource}`] ?? 0);
          if (!Number.isFinite(increment) || increment < 0 || Math.abs(increment - expected) > 1e-8) {
            throw new Error(`Placement ${resource} increment does not match VM request`);
          }
          host[`allocated_${resource}`] += increment;
        }
        if (simulateFailure) throw new Error("Simulated provisioning adapter failure after first assignment");
      }
      if (seen.size !== proposal.vms.length) throw new Error("Placement omitted a requested VM");
      for (const host of candidate) {
        for (const resource of resources) {
          if (host[`allocated_${resource}`] > host[`total_${resource}`] * safetyThreshold + 1e-8) {
            throw new Error(`Verified ${host.id} exceeds safe ${resource} limit`);
          }
        }
      }
      const nextVms = new Map(this.provisionedVms);
      for (const assignment of fresh.placement.placements) {
        const vm = proposal.vms.find(item => item.id === assignment.vm_id);
        if (!vm) throw new Error("Verified placement omitted a VM record");
        nextVms.set(vm.id, { id: vm.id, host_id: assignment.host_id,
          cpu: vm.cpu_required, memory: vm.memory_required, network: vm.network_required });
      }
      this.inventory = candidate;
      this.provisionedVms = nextVms;
      proposal.decision = fresh;
      proposal.status = "SUCCEEDED";
      proposal.reason = "Simulated allocation committed and verified against host limits";
      proposal.verification = { passed: true, message: proposal.reason, hosts: this.hosts() };
    } catch (error) {
      proposal.status = "FAILED";
      proposal.reason = error instanceof Error ? error.message : "Simulated execution failed";
      proposal.verification = { passed: false, message: `${proposal.reason}; inventory unchanged`, hosts: this.hosts() };
    } finally {
      proposal.updated_at = new Date().toISOString();
      this.executing = false;
    }
    return proposal;
  }
}

export const provisioner = new SimulatedProvisioner([
  { id: "Host-01", total_cpu: 8, total_memory: 16, total_network: 1_000_000, allocated_cpu: 2, allocated_memory: 4, allocated_network: 100_000 },
  { id: "Host-02", total_cpu: 12, total_memory: 32, total_network: 1_000_000, allocated_cpu: 5, allocated_memory: 10, allocated_network: 220_000 },
  { id: "Host-03", total_cpu: 16, total_memory: 32, total_network: 10_000_000, allocated_cpu: 3, allocated_memory: 8, allocated_network: 400_000 },
]);
