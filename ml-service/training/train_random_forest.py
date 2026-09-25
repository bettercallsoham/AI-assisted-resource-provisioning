import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prediction.lstm_predictor import LSTMPredictor


DEFAULT_DATASET = ROOT / "data" / "final_dataset.csv"
MODEL_DIR = ROOT / "models"
FEATURE_NAMES = [
    "predicted_request_rate",
    "current_request_rate",
    "cpu_utilization",
    "memory_utilization",
    "network_throughput",
    "response_latency",
]
TARGETS = {
    "cpu": "cpu_utilization",
    "memory": "memory_utilization",
    "network": "network_throughput",
}


def load_resource_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", "request_rate", *TARGETS.values(), "response_latency"}
    missing_columns = required.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing columns: {sorted(missing_columns)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    numeric_columns = ["request_rate", *TARGETS.values(), "response_latency"]
    frame[numeric_columns] = frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    missing_values = frame[["timestamp", *numeric_columns]].isna().sum()
    if missing_values.any():
        raise ValueError(f"Dataset contains missing values: {missing_values[missing_values > 0].to_dict()}")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("Dataset contains duplicate timestamps")
    return frame[["timestamp", *numeric_columns]]


def chronological_split(frame: pd.DataFrame, train_ratio: float = 0.7, validation_ratio: float = 0.15):
    train_end = int(len(frame) * train_ratio)
    validation_end = train_end + int(len(frame) * validation_ratio)
    if train_end == 0 or validation_end >= len(frame):
        raise ValueError("Dataset is too small for the requested chronological split")
    return frame.iloc[:train_end], frame.iloc[train_end:validation_end], frame.iloc[validation_end:]


def build_supervised_data(frame: pd.DataFrame, window: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    request_rates = frame["request_rate"].to_numpy(dtype=float)
    if len(request_rates) <= window + 1:
        raise ValueError("Dataset is too small for the LSTM lookback window")
    lstm_predictor = LSTMPredictor()
    histories = np.array([
        request_rates[index - window + 1:index + 1]
        for index in range(window, len(request_rates) - 1)
    ])
    predicted_rates = lstm_predictor.predict_many(histories)
    current_rows = frame.iloc[window:-1]
    next_rows = frame.iloc[window + 1:]
    features = np.column_stack([
        predicted_rates,
        current_rows["request_rate"].to_numpy(dtype=float),
        current_rows["cpu_utilization"].to_numpy(dtype=float),
        current_rows["memory_utilization"].to_numpy(dtype=float),
        current_rows["network_throughput"].to_numpy(dtype=float),
        current_rows["response_latency"].to_numpy(dtype=float),
    ])
    targets = {
        resource: next_rows[column].to_numpy(dtype=float)
        for resource, column in TARGETS.items()
    }
    return features, targets


def train(dataset: Path, epochs: int = 100, window: int = 12) -> dict[str, dict[str, float | int]]:
    frame = load_resource_frame(dataset)
    features, targets = build_supervised_data(frame, window)
    train_end = int(len(features) * 0.7)
    validation_end = train_end + int(len(features) * 0.15)
    if train_end == 0 or validation_end >= len(features):
        raise ValueError("Dataset is too small for the requested chronological split")
    x_train, x_validation, x_test = features[:train_end], features[train_end:validation_end], features[validation_end:]
    scaler = StandardScaler().fit(x_train)
    x_train_scaled = scaler.transform(x_train)
    x_validation_scaled = scaler.transform(x_validation)
    x_test_scaled = scaler.transform(x_test)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, MODEL_DIR / "rf_scaler.joblib")
    results = {}
    for resource, target in targets.items():
        y_train, y_validation, y_test = target[:train_end], target[train_end:validation_end], target[validation_end:]
        model = RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            min_samples_leaf=2,
            n_jobs=-1,
        )
        model.fit(x_train_scaled, y_train)
        validation_prediction = model.predict(x_validation_scaled)
        test_prediction = model.predict(x_test_scaled)
        results[resource] = {
            "mae": float(mean_absolute_error(y_test, test_prediction)),
            "rmse": float(np.sqrt(mean_squared_error(y_test, test_prediction))),
            "r2": float(r2_score(y_test, test_prediction)),
            "train_rows": int(len(y_train)),
            "validation_rows": int(len(y_validation)),
            "test_rows": int(len(y_test)),
            "validation_mae": float(mean_absolute_error(y_validation, validation_prediction)),
        }
        joblib.dump(model, MODEL_DIR / f"rf_{resource}.joblib")
    metrics_path = MODEL_DIR / "rf_metrics.json"
    metrics_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Random Forest resource-demand regressors")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--window", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(train(args.dataset, window=args.window), indent=2))


if __name__ == "__main__":
    main()