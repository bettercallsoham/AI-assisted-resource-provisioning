"""Validate explicit VM requests; model forecasts remain observational signals."""

from datetime import datetime, timezone

from models import CapacityDecision, Infrastructure, RESOURCES
from placement import place_vms


def assess_capacity(infrastructure: Infrastructure, predicted: dict[str, float] | None = None,
                    safety_threshold: float = 0.8) -> CapacityDecision:
    placement = place_vms(infrastructure.hosts, infrastructure.vms, safety_threshold)
    available = {resource: sum(host.remaining()[resource] for host in infrastructure.hosts)
                 for resource in RESOURCES}
    safe = {resource: sum(max(0.0, getattr(host, f"total_{resource}") * safety_threshold
                              - getattr(host, f"allocated_{resource}")) for host in infrastructure.hosts)
            for resource in RESOURCES}
    increment = {resource: sum(vm.increment()[resource] for vm in infrastructure.vms)
                 for resource in RESOURCES}

    if not placement["feasible"]:
        physical = [resource for resource in RESOURCES if increment[resource] > available[resource] + 1e-9]
        safe_limited = [resource for resource in RESOURCES if increment[resource] > safe[resource] + 1e-9]
        bottleneck = (physical or safe_limited or ["placement"])[0]
        decision = "OVERLOAD" if physical else "REJECTED"
        reason = (f"Requested {bottleneck} increment exceeds physical capacity" if physical else
                  f"No placement satisfies per-host safe limits; limiting resource: {bottleneck}")
    elif any(increment.values()):
        decision, bottleneck, reason = "RECOMMEND", "none", "Explicit VM request fits per-host safe capacity"
    else:
        decision, bottleneck, reason = "HOLD", "none", "No additional allocation requested"

    return CapacityDecision(
        decision=decision,
        bottleneck=bottleneck,
        predicted_indicators=predicted or {},
        available_capacity=available,
        reason=reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
        placement=placement,
        feasible=placement["feasible"],
        requested_increment=increment,
        safe_available_capacity=safe,
    )
