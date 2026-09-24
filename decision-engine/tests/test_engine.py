import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from capacity import assess_capacity
from models import Host, Infrastructure, VM
from placement import place_vms


def test_enough_capacity_holds():
    result = assess_capacity(Infrastructure([Host("h1", 10, 20, 100)]), {"cpu": 4, "memory": 5, "network": 20})
    assert result.decision == "HOLD"


def test_cpu_pressure_scales_up():
    result = assess_capacity(Infrastructure([Host("h1", 10, 20, 100, 2, 2, 2)]), {"cpu": 7, "memory": 3, "network": 3})
    assert result.decision == "SCALE_UP"
    assert result.bottleneck == "cpu"


def test_best_fit_and_unplaced():
    hosts = [Host("h1", 8, 16, 100), Host("h2", 12, 32, 100)]
    result = place_vms(hosts, [VM("vm1", 6, 8, 10), VM("vm2", 7, 20, 10), VM("vm3", 20, 20, 10)])
    assert len(result["placements"]) == 2
    assert result["unplaced"] == ["vm3"]