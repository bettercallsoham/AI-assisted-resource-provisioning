import csv
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workload-generator"))

from collect_session import FIELDS, collect_session, complete_row, sha256
from metric_semantics import effective_memory_limit, non_loopback_bytes


def responses(timestamp=100.0):
    return {field: {"status": "success", "data": {"result": [
        {"value": [timestamp, "4.0"]}]}} for field in FIELDS[1:]}


class MetricSemanticsTests(unittest.TestCase):
    def test_unlimited_cgroup_value_falls_back_to_physical_memory(self):
        self.assertEqual(effective_memory_limit(16_000, ["max", "9223372036854771712"]), 16_000)
        self.assertEqual(effective_memory_limit(16_000, ["8000"]), 8_000)

    def test_network_excludes_loopback(self):
        counters = {"lo": SimpleNamespace(bytes_sent=100, bytes_recv=100),
                    "eth0": SimpleNamespace(bytes_sent=20, bytes_recv=30)}
        self.assertEqual(non_loopback_bytes(counters), 50)


class SessionTests(unittest.TestCase):
    def test_rejects_stale_skewed_and_missing_responses(self):
        self.assertIsNotNone(complete_row(responses(), 5, 100)[1])
        self.assertIsNotNone(complete_row(responses(), 5, None, observed_at=200)[1])
        skewed = responses()
        skewed["network_throughput"]["data"]["result"][0]["value"][0] = 110
        self.assertIsNotNone(complete_row(skewed, 5, None)[1])
        missing = responses()
        missing["response_latency"]["data"]["result"] = []
        self.assertIsNotNone(complete_row(missing, 5, None)[1])

    def test_session_is_traceable_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("collect_session.query_raw", side_effect=lambda url, query: responses(time.time())[FIELDS[1]]):
                result = collect_session("run_01", "heldout", root, "http://unused", 0.25,
                                         1, "test scenario", "test environment")
            directory = root / "run_01"
            with (directory / "metrics.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(manifest["complete_rows"], len(rows))
            self.assertEqual(manifest["role"], "heldout")
            self.assertEqual(manifest["metrics_sha256"], sha256(directory / "metrics.csv"))
            self.assertEqual(manifest["raw_sha256"], sha256(directory / "prometheus_responses.ndjson"))
            with self.assertRaises(FileExistsError):
                collect_session("run_01", "heldout", root, "http://unused", 0.01,
                                1, "test scenario", "test environment")


if __name__ == "__main__":
    unittest.main()
