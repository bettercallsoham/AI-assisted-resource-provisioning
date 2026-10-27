from dataclasses import dataclass, field
from math import isfinite
from typing import Optional


RESOURCES = ("cpu", "memory", "network")


def _check_amount(name: str, value: float, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if (positive and value <= 0) or (not positive and value < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")


@dataclass
class Host:
    id: str
    total_cpu: float
    total_memory: float
    total_network: float
    allocated_cpu: float = 0
    allocated_memory: float = 0
    allocated_network: float = 0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("host id is required")
        for resource in RESOURCES:
            total = getattr(self, f"total_{resource}")
            allocated = getattr(self, f"allocated_{resource}")
            _check_amount(f"host {self.id} total_{resource}", total, positive=True)
            _check_amount(f"host {self.id} allocated_{resource}", allocated)
            if allocated > total:
                raise ValueError(f"host {self.id} allocated_{resource} exceeds total_{resource}")

    def remaining(self) -> dict[str, float]:
        return {resource: getattr(self, f"total_{resource}") - getattr(self, f"allocated_{resource}") for resource in RESOURCES}


@dataclass
class VM:
    id: str
    cpu_required: float
    memory_required: float
    network_required: float
    host_id: Optional[str] = None
    current_cpu: float = 0
    current_memory: float = 0
    current_network: float = 0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("VM id is required")
        for resource in RESOURCES:
            required = getattr(self, f"{resource}_required")
            current = getattr(self, f"current_{resource}")
            _check_amount(f"VM {self.id} {resource}_required", required)
            _check_amount(f"VM {self.id} current_{resource}", current)
            if current > required:
                raise ValueError(f"VM {self.id} current_{resource} exceeds {resource}_required; scale-down is not supported")
        if any(getattr(self, f"current_{resource}") > 0 for resource in RESOURCES) and not self.host_id:
            raise ValueError(f"VM {self.id} has current allocation but no host_id")
        if self.host_id is None and not any(getattr(self, f"{resource}_required") > 0 for resource in RESOURCES):
            raise ValueError(f"VM {self.id} has no requested resources")

    def increment(self) -> dict[str, float]:
        return {resource: getattr(self, f"{resource}_required") - getattr(self, f"current_{resource}") for resource in RESOURCES}


@dataclass
class CapacityDecision:
    decision: str
    bottleneck: str
    predicted_indicators: dict[str, float]
    available_capacity: dict[str, float]
    reason: str
    timestamp: str
    placement: dict = field(default_factory=dict)
    feasible: bool = False
    requested_increment: dict[str, float] = field(default_factory=dict)
    safe_available_capacity: dict[str, float] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=lambda: {"cpu": "vCPU", "memory": "GiB", "network": "B/s"})


@dataclass
class Infrastructure:
    hosts: list[Host] = field(default_factory=list)
    vms: list[VM] = field(default_factory=list)

    def __post_init__(self) -> None:
        for label, items in (("host", self.hosts), ("VM", self.vms)):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {label} id")
        host_ids = {host.id for host in self.hosts}
        if any(vm.host_id and vm.host_id not in host_ids for vm in self.vms):
            raise ValueError("VM host_id does not identify a supplied host")
