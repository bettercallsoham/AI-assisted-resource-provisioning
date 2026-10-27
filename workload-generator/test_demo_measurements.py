import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_measurements import projected_request_rate, traffic_readings


class ProjectionTests(unittest.TestCase):
    def test_forecast_tracks_steady_and_transition_windows(self):
        normal = projected_request_rate("walkthrough", 40)
        transition = projected_request_rate("walkthrough", 55)
        high = projected_request_rate("walkthrough", 80)
        self.assertAlmostEqual(normal, 5, delta=0.5)
        self.assertGreater(transition, normal)
        self.assertLess(transition, high)
        self.assertAlmostEqual(high, 20, delta=1.5)

    def test_projection_is_close_to_five_second_counter_samples(self):
        observed_rate = sum(traffic_readings("high", second)[0] * 5 for second in range(50, 80, 5)) / 30
        self.assertAlmostEqual(projected_request_rate("walkthrough", 75), observed_rate, delta=1.5)


if __name__ == "__main__":
    unittest.main()
