from models import Host, VM


def place_vms(hosts: list[Host], vms: list[VM]) -> dict:
    placements = []
    unplaced = []
    ordered = sorted(vms, key=lambda vm: (max(vm.cpu_required, vm.memory_required, vm.network_required), vm.id), reverse=True)
    for vm in ordered:
        feasible = []
        for host in hosts:
            remaining = host.remaining()
            if remaining["cpu"] >= vm.cpu_required and remaining["memory"] >= vm.memory_required and remaining["network"] >= vm.network_required:
                waste = sum((remaining[resource] - requirement) / max(getattr(host, f"total_{resource}"), 1) for resource, requirement in (("cpu", vm.cpu_required), ("memory", vm.memory_required), ("network", vm.network_required)))
                feasible.append((waste, host.id, host))
        if not feasible:
            unplaced.append(vm.id)
            continue
        _, _, selected = min(feasible, key=lambda item: (item[0], item[1]))
        selected.allocated_cpu += vm.cpu_required
        selected.allocated_memory += vm.memory_required
        selected.allocated_network += vm.network_required
        vm.host_id = selected.id
        placements.append({"vm_id": vm.id, "host_id": selected.id})
    return {"placements": placements, "unplaced": unplaced, "hosts": [{"id": host.id, "remaining": host.remaining()} for host in hosts]}