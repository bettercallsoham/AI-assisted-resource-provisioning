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

    def explain(self, resource: str, values: np.ndarray) -> dict:
        if resource not in RESOURCE_NAMES:
            raise ValueError(f"Unsupported resource: {resource}")
        if values.shape != (1, len(FEATURE_NAMES)):
            raise ValueError(f"values must have shape (1, {len(FEATURE_NAMES)})")
        import shap

        scaled = self.scaler.transform(values)
        model = self.models[resource]
        explanation = shap.TreeExplainer(model)(scaled)
        contributions = np.asarray(explanation.values)
        if contributions.ndim == 3:
            contributions = contributions[0, :, 0]
        else:
            contributions = contributions[0]
        prediction = float(model.predict(scaled)[0])
        base_values = np.asarray(explanation.base_values).reshape(-1)
        feature_contributions = [
            {
                "name": name,
                "value": float(values[0, index]),
                "contribution": float(contribution),
                "direction": "positive" if contribution >= 0 else "negative",
            }
            for index, (name, contribution) in enumerate(zip(FEATURE_NAMES, contributions))
        ]
        ranked_importance = sorted(
            [
                {"name": item["name"], "importance": abs(item["contribution"])}
                for item in feature_contributions
            ],
            key=lambda item: item["importance"],
            reverse=True,
        )
        return {
            "resource": resource,
            "prediction": prediction,
            "base_value": float(base_values[0]),
            "feature_names": FEATURE_NAMES,
            "features": feature_contributions,
            "ranked_importance": ranked_importance,
        }


def predict_resources(**features: float) -> dict[str, float]:
    missing = set(FEATURE_NAMES).difference(features)
    if missing:
        raise ValueError(f"Missing resource prediction features: {sorted(missing)}")
    return ResourcePredictor().predict(**{name: features[name] for name in FEATURE_NAMES})