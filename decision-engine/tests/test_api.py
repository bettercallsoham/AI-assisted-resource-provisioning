import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient
from main import app


class DecisionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.request = {
            "hosts": [{"id": "h1", "total_cpu": 8, "total_memory": 16, "total_network": 1_000_000}],
            "vms": [{"id": "vm1", "cpu_required": 2, "memory_required": 4,
                     "network_required": 100_000}],
        }

    def test_decision_response_is_consistent_with_placement(self):
        response = self.client.post("/decision", json=self.request)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["decision"], "RECOMMEND")
        self.assertTrue(result["feasible"])
        self.assertTrue(result["placement"]["feasible"])
        self.assertEqual(result["units"], {"cpu": "vCPU", "memory": "GiB", "network": "B/s"})
        placement = self.client.post("/placement", json=self.request)
        self.assertEqual(placement.status_code, 200)
        self.assertEqual(placement.json(), result["placement"])
        self.request["vms"][0]["cpu_required"] = 20
        rejected = self.client.post("/decision", json=self.request).json()
        self.assertEqual(rejected["decision"], "OVERLOAD")
        self.assertFalse(rejected["feasible"])
        self.assertEqual(rejected["placement"]["placements"], [])

    def test_invalid_inventory_is_client_error(self):
        self.request["hosts"][0]["allocated_cpu"] = 9
        response = self.client.post("/decision", json=self.request)
        self.assertEqual(response.status_code, 422)
        self.assertIn("exceeds", response.json()["detail"])

    def test_live_response_keeps_predictions_informational(self):
        observed = {"timestamp": "2026-01-01T00:00:00Z", "request_rate": 4.0,
                    "cpu": 20.0, "memory": 30.0, "network": 2_000.0, "latency": 10.0}
        forecast = {"predicted_request_rate": 5.0, "model": "lstm",
                    "origin_timestamp": "2026-01-01T00:00:00+00:00",
                    "target_timestamp": "2026-01-01T00:00:05+00:00"}
        history = [{"timestamp": "2026-01-01T00:00:00+00:00", "value": 4.0}]
        predictions = {"predicted_cpu": 95.0, "predicted_memory": 90.0,
                       "predicted_network": 100_000_000.0}
        with patch("main.run_ml_pipeline", return_value=(observed, forecast, predictions, {}, history)):
            response = self.client.post("/decision/live", json=self.request)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["predicted_network"], 100_000_000.0)
        self.assertEqual(result["predicted_workload"]["target_timestamp"],
                         "2026-01-01T00:00:05+00:00")
        self.assertEqual(result["request_history"], history)
        self.assertEqual(result["decision"], "RECOMMEND")
        self.assertTrue(result["capacity_status"]["feasible"])
        self.assertEqual(result["placement"]["placements"][0]["increment"]["network"], 100_000)


if __name__ == "__main__":
    unittest.main()
