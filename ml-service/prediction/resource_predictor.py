from pathlib import Path

import joblib
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
FEATURE_NAMES = [
    "predicted_request_rate",
    "current_request_rate",
    "cpu_utilization",
    "memory_utilization",
    "network_throughput",
    "response_latency",
]
RESOURCE_NAMES = ("cpu", "memory", "network")


class ResourcePredictor:
    def __init__(self, model_dir: str | Path = MODEL_DIR):
        model_dir = Path(model_dir)
        self.scaler = joblib.load(model_dir / "rf_scaler.joblib")
        self.models = {
            resource: joblib.load(model_dir / f"rf_{resource}.joblib")
            for resource in RESOURCE_NAMES
        }

    def predict(
        self,
        predicted_request_rate: float,
        current_request_rate: float,
        cpu_utilization: float,
        memory_utilization: float,
        network_throughput: float,
        response_latency: float,
    ) -> dict[str, float]:
        values = np.array(
            [[
                predicted_request_rate,
                current_request_rate,
                cpu_utilization,
                memory_utilization,
                network_throughput,
                response_latency,
            ]],
            dtype=float,
        )
        scaled = self.scaler.transform(values)
        return {
            f"predicted_{resource}": max(0.0, float(model.predict(scaled)[0]))
            for resource, model in self.models.items()
        }


def predict_resources(**features: float) -> dict[str, float]:
    missing = set(FEATURE_NAMES).difference(features)
    if missing:
        raise ValueError(f"Missing resource prediction features: {sorted(missing)}")
    return ResourcePredictor().predict(**{name: features[name] for name in FEATURE_NAMES})