from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Host:
    id: str
    total_cpu: float
    total_memory: float
    total_network: float
    allocated_cpu: float = 0
    allocated_memory: float = 0
    allocated_network: float = 0

    def remaining(self) -> dict[str, float]:
        return {"cpu": self.total_cpu - self.allocated_cpu, "memory": self.total_memory - self.allocated_memory, "network": self.total_network - self.allocated_network}


@dataclass
class VM:
    id: str
    cpu_required: float
    memory_required: float
    network_required: float
    host_id: Optional[str] = None


@dataclass
class CapacityDecision:
    decision: str
    bottleneck: str
    predicted_demand: dict[str, float]
    available_capacity: dict[str, float]
    reason: str
    timestamp: str


@dataclass
class Infrastructure:
    hosts: list[Host] = field(default_factory=list)
    vms: list[VM] = field(default_factory=list)