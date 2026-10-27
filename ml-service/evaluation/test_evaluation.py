import csv
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_data import audit
from evaluate import score
from evaluate_forecast_session import matched_windows


class EvaluationTests(unittest.TestCase):
    def test_session_windows_match_future_timestamp_and_skip_gaps(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = [(start + timedelta(seconds=5 * index), float(index)) for index in range(14)]
        self.assertEqual(matched_windows(rows, 12), [12, 13])
        rows[12] = (rows[12][0] + timedelta(seconds=5), rows[12][1])
        self.assertEqual(matched_windows(rows, 12), [])

    def test_zero_target_has_no_wape(self):
        result = score([0, 0], [0, 1], 1)
        self.assertIsNone(result["wape"])
        self.assertEqual(result["mae"], 0.5)

    def test_high_load_underprediction(self):
        result = score([1, 10, 20], [1, 8, 25], 10)
        self.assertEqual(result["high_load_rows"], 2)
        self.assertEqual(result["high_load_underprediction_mae"], 1)

    def test_audit_detects_duplicates_and_bad_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["timestamp", "request_rate", "cpu_utilization", "memory_utilization",
                                 "network_throughput", "response_latency"])
                writer.writerow(["2026-01-01T00:00:00Z", 1, 2, 3, 4, 5])
                writer.writerow(["2026-01-01T00:00:00Z", 1, 2, 3, "nan", 5])
            result = audit(path)
            self.assertEqual(result["duplicate_timestamps"], 1)
            self.assertEqual(result["missing_or_nonfinite"]["network_throughput"], 1)


if __name__ == "__main__":
    unittest.main()
