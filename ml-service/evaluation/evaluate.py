"""Evaluate saved LSTM/RF artifacts and causal baselines without modifying them."""

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"request_rate": "req/s", "cpu_utilization": "percentage points",
          "memory_utilization": "percentage points", "network_throughput": "B/s"}
WINDOW = 12


def load(path: Path) -> dict[str, list[float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 100:
        raise ValueError("Evaluation requires enough chronological rows for train/validation/test")
    return {name: [float(row[name]) for row in rows] for name in FIELDS | {"response_latency": "ms"}}


def score(actual: list[float], predicted: list[float], threshold: float) -> dict:
    if len(actual) != len(predicted) or not actual:
        raise ValueError("Metrics require aligned nonempty vectors")
    errors = [forecast - target for target, forecast in zip(actual, predicted)]
    high = [index for index, target in enumerate(actual) if target >= threshold]
    return {
        "rows": len(actual),
        "mae": statistics.mean(abs(error) for error in errors),
        "rmse": math.sqrt(statistics.mean(error * error for error in errors)),
        "wape": sum(abs(error) for error in errors) / sum(abs(target) for target in actual)
                if sum(abs(target) for target in actual) else None,
        "bias": statistics.mean(errors),
        "high_load_rows": len(high),
        "high_load_mae": statistics.mean(abs(errors[index]) for index in high) if high else None,
        "high_load_underprediction_mae": statistics.mean(max(0.0, -errors[index]) for index in high) if high else None,
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def evaluate(dataset: Path, legacy_models: bool) -> dict:
    series = load(dataset)
    n = len(series["request_rate"])
    train_end = int(n * 0.70)
    validation_end = train_end + int(n * 0.15)
    # Legacy RF test starts at target 4251 for n=5000. All methods use the
    # same origins when legacy artifacts are compared.
    first_target = max(validation_end, WINDOW + 1) + (1 if legacy_models else 0)
    indices = list(range(first_target, n))
    result = {
        "dataset": str(dataset), "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "target_horizon_rows": 1, "window": WINDOW,
        "split": {"train_target_end_exclusive": train_end,
                  "validation_target_end_exclusive": validation_end,
                  "first_evaluated_test_target": first_target, "test_rows": len(indices)},
        "artifact_status": "legacy_unverified_provenance" if legacy_models else "baselines_only",
        "targets": {},
    }
    for name, unit in FIELDS.items():
        values = series[name]
        actual = [values[index] for index in indices]
        threshold = percentile(values[:train_end], 0.75)
        result["targets"][name] = {
            "unit": unit, "high_load_threshold_from_train": threshold,
            "persistence": score(actual, [values[index - 1] for index in indices], threshold),
            "trailing_12_mean": score(actual,
                                      [statistics.mean(values[index - WINDOW:index]) for index in indices],
                                      threshold),
        }
    if legacy_models:
        sys.path.insert(0, str(ROOT))
        import numpy as np
        import tensorflow as tf
        import sklearn
        from prediction.lstm_predictor import LSTMPredictor
        from prediction.resource_predictor import ResourcePredictor

        lstm = LSTMPredictor()
        rf = ResourcePredictor()
        histories = np.asarray([series["request_rate"][index - WINDOW:index] for index in indices])
        forecast_rates = lstm.predict_many(histories)
        result["versions"] = {"tensorflow": tf.__version__, "keras": tf.keras.__version__,
                              "sklearn": sklearn.__version__}
        result["targets"]["request_rate"]["lstm"] = score(
            [series["request_rate"][index] for index in indices], forecast_rates.tolist(),
            result["targets"]["request_rate"]["high_load_threshold_from_train"])
        features = np.asarray([
            [forecast_rates[position], series["request_rate"][index - 1],
             series["cpu_utilization"][index - 1], series["memory_utilization"][index - 1],
             series["network_throughput"][index - 1], series["response_latency"][index - 1]]
            for position, index in enumerate(indices)
        ])
        scaled = rf.scaler.transform(features)
        for short, name in (("cpu", "cpu_utilization"), ("memory", "memory_utilization"),
                            ("network", "network_throughput")):
            predictions = np.maximum(0, rf.models[short].predict(scaled)).tolist()
            result["targets"][name]["legacy_lstm_rf_pipeline"] = score(
                [series[name][index] for index in indices], predictions,
                result["targets"][name]["high_load_threshold_from_train"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "final_dataset.csv")
    parser.add_argument("--legacy-models", action="store_true")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, args.legacy_models), indent=2))


if __name__ == "__main__":
    main()
