from datetime import datetime, timezone

from models import CapacityDecision, Infrastructure


def assess_capacity(infrastructure: Infrastructure, predicted: dict[str, float], safety_threshold: float = 0.8) -> CapacityDecision:
    available = {resource: sum(host.remaining()[resource] for host in infrastructure.hosts) for resource in ("cpu", "memory", "network")}
    safe = {resource: sum(host.total_cpu if resource == "cpu" else host.total_memory if resource == "memory" else host.total_network for host in infrastructure.hosts) * safety_threshold - sum(getattr(host, f"allocated_{resource}") for host in infrastructure.hosts) for resource in available}
    if any(predicted[resource] > available[resource] for resource in predicted):
        bottleneck = max(predicted, key=lambda resource: predicted[resource] / max(available[resource], 0.001))
        return CapacityDecision("OVERLOAD", bottleneck, predicted, available, f"Predicted {bottleneck} demand exceeds physical capacity", datetime.now(timezone.utc).isoformat())
    exceeded = [resource for resource in predicted if predicted[resource] > max(0, safe[resource])]
    if exceeded:
        bottleneck = max(exceeded, key=lambda resource: predicted[resource] / max(safe[resource], 0.001))
        return CapacityDecision("SCALE_UP", bottleneck, predicted, available, f"Predicted {bottleneck} demand exceeds available safe capacity", datetime.now(timezone.utc).isoformat())
    return CapacityDecision("HOLD", "none", predicted, available, "Predicted demand fits within configured safe capacity", datetime.now(timezone.utc).isoformat())