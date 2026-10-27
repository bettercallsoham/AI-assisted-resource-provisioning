"""Pure helpers for the workload's exported memory and network measurements."""


def effective_memory_limit(host_total: int, cgroup_values: list[str]) -> int:
    """Use the smallest finite cgroup limit, never a sentinel above physical RAM."""
    if host_total <= 0:
        raise ValueError("Physical memory must be positive")
    candidates = [host_total]
    for raw in cgroup_values:
        try:
            value = int(raw.strip())
        except ValueError:
            continue
        if 0 < value <= host_total:
            candidates.append(value)
    return min(candidates)


def non_loopback_bytes(counters: dict) -> int:
    """Combined sent and received bytes visible to this network namespace."""
    return sum(
        item.bytes_sent + item.bytes_recv
        for name, item in counters.items()
        if name != "lo" and not name.lower().startswith("loopback")
    )
