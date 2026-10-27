import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from integration import IntegrationError, request_rate_history, run_ml_pipeline


class ForecastTimingTests(unittest.TestCase):
    def test_history_uses_twelve_aligned_fresh_samples(self):
        values = [[40 + 5 * index, str(index)] for index in range(12)]
        with patch("integration.time.time", return_value=100), \
             patch("integration._get_json", return_value={"data": {"result": [{"values": values}]}}), \
             patch("integration._query", return_value=96):
            result = request_rate_history()
        self.assertEqual(len(result), 12)
        self.assertEqual(result[-1]["timestamp"], "1970-01-01T00:01:35+00:00")
        self.assertEqual(result[-1]["value"], 11)

    def test_gapped_or_stale_history_is_rejected(self):
        values = [[40 + 5 * index, str(index)] for index in range(12)]
        values[4][0] += 1
        with patch("integration.time.time", return_value=100), \
             patch("integration._get_json", return_value={"data": {"result": [{"values": values}]}}), \
             patch("integration._query", return_value=96):
            with self.assertRaisesRegex(IntegrationError, "aligned"):
                request_rate_history()
        values[4][0] -= 1
        with patch("integration.time.time", return_value=100), \
             patch("integration._get_json", return_value={"data": {"result": [{"values": values}]}}), \
             patch("integration._query", return_value=80):
            with self.assertRaisesRegex(IntegrationError, "stale"):
                request_rate_history()

    def test_forecast_target_is_five_seconds_after_last_input(self):
        history = [{"timestamp": f"2026-01-01T00:00:{index * 5:02d}+00:00", "value": float(index)}
                   for index in range(12)]
        metrics = {"request_rate": 11, "cpu": 2, "memory": 3, "network": 4,
                   "latency": 5, "timestamp": history[-1]["timestamp"]}
        calls = []

        def ml(path, body):
            calls.append((path, body))
            if path == "/predict/workload":
                return {"predicted_request_rate": 12, "model": "lstm"}
            return {"predicted_cpu": 1, "predicted_memory": 1, "predicted_network": 1}

        with patch("integration.request_rate_history", return_value=history), \
             patch("integration.current_metrics", return_value=metrics) as current, \
             patch("integration.planned_workload", return_value=None), \
             patch("integration.post_ml", side_effect=ml):
            observed, forecast, _, _, returned = run_ml_pipeline()
        current.assert_called_once_with(history[-1])
        self.assertEqual(observed["timestamp"], forecast["origin_timestamp"])
        self.assertEqual(forecast["target_timestamp"], "2026-01-01T00:01:00+00:00")
        self.assertEqual(calls[0][1]["history"], [float(index) for index in range(12)])
        self.assertEqual(returned, history)

    def test_demo_projection_uses_target_time_without_calling_lstm(self):
        history = [{"timestamp": "2026-01-01T00:00:55+00:00", "value": 19.5}]
        metrics = {"request_rate": 19.5, "cpu": 70, "memory": 65, "network": 300000,
                   "latency": 120, "timestamp": history[-1]["timestamp"]}
        with patch("integration.request_rate_history", return_value=history), \
             patch("integration.current_metrics", return_value=metrics), \
             patch("integration.planned_workload", return_value={"predicted_request_rate": 20, "model": "scenario"}) as planned, \
             patch("integration.post_ml", return_value={"predicted_cpu": 70, "predicted_memory": 65,
                                                        "predicted_network": 300000}) as ml:
            _, forecast, _, _, _ = run_ml_pipeline()
        planned.assert_called_once()
        self.assertEqual(forecast["target_timestamp"], "2026-01-01T00:01:00+00:00")
        self.assertEqual(forecast["predicted_request_rate"], 20)
        self.assertTrue(all(call.args[0] != "/predict/workload" for call in ml.call_args_list))


if __name__ == "__main__":
    unittest.main()
