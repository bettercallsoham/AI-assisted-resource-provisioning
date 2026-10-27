import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from capacity import assess_capacity
from models import Host, Infrastructure, VM
from placement import place_vms


class DecisionEngineTests(unittest.TestCase):
    def test_sufficient_capacity_produces_feasible_plan(self):
        infra = Infrastructure([Host("h1", 10, 20, 1_000_000)], [VM("new", 2, 4, 100_000)])
        result = assess_capacity(infra)
        self.assertEqual(result.decision, "RECOMMEND")
        self.assertTrue(result.feasible)
        self.assertEqual(result.placement["placements"][0]["host_id"], "h1")
        self.assertEqual(result.requested_increment, {"cpu": 2, "memory": 4, "network": 100_000})
        self.assertEqual(infra.hosts[0].allocated_cpu, 0)  # planning is side-effect free

    def test_incremental_resize_does_not_double_count_existing_allocation(self):
        host = Host("h1", 10, 20, 1_000_000, 5, 10, 400_000)
        vm = VM("existing", 6, 12, 500_000, "h1", 4, 8, 300_000)
        result = assess_capacity(Infrastructure([host], [vm]))
        self.assertEqual(result.requested_increment, {"cpu": 2, "memory": 4, "network": 200_000})
        self.assertTrue(result.feasible)
        self.assertEqual(result.placement["hosts"][0]["remaining"],
                         {"cpu": 3, "memory": 6, "network": 400_000})
        self.assertEqual(host.allocated_network, 400_000)

    def test_insufficient_physical_capacity_rejects_whole_plan(self):
        infra = Infrastructure([Host("h1", 4, 8, 100_000)], [VM("small", 1, 1, 10_000), VM("large", 5, 2, 20_000)])
        result = assess_capacity(infra)
        self.assertEqual(result.decision, "OVERLOAD")
        self.assertFalse(result.feasible)
        self.assertEqual(result.placement["placements"], [])
        self.assertIn("large", result.placement["unplaced"])

    def test_per_host_safe_limit_rejects_even_if_aggregate_physical_fits(self):
        infra = Infrastructure([Host("h1", 4, 8, 100_000), Host("h2", 4, 8, 100_000)],
                               [VM("too-large-for-one-host", 4, 1, 10_000)])
        result = assess_capacity(infra)
        self.assertEqual(result.decision, "REJECTED")
        self.assertFalse(result.feasible)
        self.assertEqual(result.placement["placements"], [])

    def test_invalid_inventory_and_request(self):
        with self.assertRaises(ValueError):
            Host("h1", 4, 8, 100_000, allocated_cpu=5)
        with self.assertRaises(ValueError):
            Host("h1", float("nan"), 8, 100_000)
        with self.assertRaises(ValueError):
            VM("vm", 2, 1, 10, current_cpu=1)
        with self.assertRaises(ValueError):
            Infrastructure([Host("same", 4, 8, 100_000), Host("same", 4, 8, 100_000)])
        with self.assertRaises(ValueError):
            place_vms([Host("h1", 4, 8, 100_000)], [VM("vm", 1, 1, 10)], float("nan"))

    def test_prediction_is_informational_and_decision_matches_placement(self):
        infra = Infrastructure([Host("h1", 10, 20, 1_000_000)], [VM("vm", 1, 1, 10_000)])
        low = assess_capacity(infra, {"cpu": 1, "memory": 1, "network": 1})
        high = assess_capacity(infra, {"cpu": 100, "memory": 100, "network": 100_000_000})
        self.assertEqual(low.decision, high.decision)
        for result in (low, high):
            self.assertEqual(result.feasible, result.placement["feasible"])
            self.assertEqual(bool(result.placement["placements"]), result.feasible)


if __name__ == "__main__":
    unittest.main()
