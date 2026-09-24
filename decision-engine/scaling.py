from models import CapacityDecision


def choose_scaling_action(decision: CapacityDecision, current_utilization: dict[str, float] | None = None) -> str:
    if decision.decision != "HOLD":
        return decision.decision
    if current_utilization and current_utilization and max(current_utilization.values()) < 0.25:
        return "SCALE_DOWN"
    return "HOLD"