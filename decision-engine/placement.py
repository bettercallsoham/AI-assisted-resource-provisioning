"""Plan resource changes against simulated hosts without mutating supplied inventory."""

from dataclasses import replace
from math import isfinite

from models import Host, RESOURCES, VM


def place_vms(hosts: list[Host], vms: list[VM], safety_threshold: float = 0.8) -> dict:
    if not isfinite(safety_threshold) or not 0 < safety_threshold <= 1:
        raise ValueError("safety_threshold must be finite and within (0, 1]")
    if len({host.id for host in hosts}) != len(hosts) or len({vm.id for vm in vms}) != len(vms):
        raise ValueError("host and VM ids must be unique")

    inventory = {host.id: replace(host) for host in hosts}
    accounted = {host.id: {resource: 0.0 for resource in RESOURCES} for host in hosts}
    for vm in vms:
        if vm.host_id is not None:
            if vm.host_id not in inventory:
                raise ValueError(f"VM {vm.id} refers to an unknown host")
            for resource in RESOURCES:
                accounted[vm.host_id][resource] += getattr(vm, f"current_{resource}")
    for host in hosts:
        for resource in RESOURCES:
            if accounted[host.id][resource] > getattr(host, f"allocated_{resource}") + 1e-9:
                raise ValueError(f"VM current {resource} exceeds inventory allocation on {host.id}")

    def fits(host: Host, increment: dict[str, float]) -> bool:
        return all(
            getattr(host, f"allocated_{resource}") + amount
            <= getattr(host, f"total_{resource}") * safety_threshold + 1e-9
            for resource, amount in increment.items() if amount > 0
        )

    def size(vm: VM) -> float:
        if not hosts:
            return 0.0
        increment = vm.increment()
        return max(increment[resource] / max(getattr(host, f"total_{resource}") for host in hosts)
                   for resource in RESOURCES)

    # Existing VMs are pinned: resizing them never implies live migration.
    ordered = sorted(vms, key=lambda vm: (vm.host_id is None, -size(vm), vm.id))
    tentative = []
    unplaced = []
    for vm in ordered:
        increment = vm.increment()
        candidates = [inventory[vm.host_id]] if vm.host_id else list(inventory.values())
        feasible = []
        for host in candidates:
            if fits(host, increment):
                waste = sum(
                    (getattr(host, f"total_{resource}") * safety_threshold
                     - getattr(host, f"allocated_{resource}") - increment[resource])
                    / getattr(host, f"total_{resource}") for resource in RESOURCES
                )
                feasible.append((waste, host.id, host))
        if not feasible:
            unplaced.append(vm.id)
            continue
        selected = min(feasible, key=lambda item: item[:2])[2]
        for resource, amount in increment.items():
            setattr(selected, f"allocated_{resource}", getattr(selected, f"allocated_{resource}") + amount)
        tentative.append({"vm_id": vm.id, "host_id": selected.id, "increment": increment})

    all_feasible = not unplaced
    return {
        "feasible": all_feasible,
        "placements": tentative if all_feasible else [],
        "unplaced": unplaced,
        "hosts": [
            {"id": host.id, "remaining": host.remaining(),
             "safe_remaining": {resource: max(0.0, getattr(host, f"total_{resource}") * safety_threshold
                                               - getattr(host, f"allocated_{resource}")) for resource in RESOURCES}}
            for host in (inventory.values() if all_feasible else hosts)
        ],
    }
