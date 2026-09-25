from pathlib import Path

import pandas as pd
from sklearn.preprocessing import MinMaxScaler

FEATURES = ["request_rate", "cpu_utilization", "memory_utilization", "network_throughput", "response_latency"]
TARGET = "request_rate"


def load_lstm_frame(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", TARGET}
    missing_columns = required.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing columns: {sorted(missing_columns)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame[TARGET] = pd.to_numeric(frame[TARGET], errors="coerce")
    missing_values = frame[["timestamp", TARGET]].isna().sum()
    if missing_values.any():
        raise ValueError(f"Dataset contains missing values: {missing_values[missing_values > 0].to_dict()}")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("Dataset contains duplicate timestamps")
    return frame[["timestamp", TARGET]]


def load_metrics(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    frame[FEATURES] = frame[FEATURES].apply(pd.to_numeric, errors="coerce").interpolate().ffill().bfill()
    for feature in FEATURES:
        low, high = frame[feature].quantile(0.01), frame[feature].quantile(0.99)
        frame[feature] = frame[feature].clip(lower=low, upper=high)
    return frame


def make_sequences(values, window: int = 5):
    if window <= 0 or len(values) <= window:
        raise ValueError("window must be positive and smaller than the number of values")
    sequences, targets = [], []
    for index in range(len(values) - window):
        sequences.append(values[index:index + window])
        targets.append(values[index + window])
    return sequences, targets


def chronological_split(frame: pd.DataFrame, train_ratio: float = 0.7, validation_ratio: float = 0.15):
    train_end = int(len(frame) * train_ratio)
    validation_end = train_end + int(len(frame) * validation_ratio)
    return frame.iloc[:train_end], frame.iloc[train_end:validation_end], frame.iloc[validation_end:]


def fit_scaler(frame: pd.DataFrame) -> MinMaxScaler:
    return MinMaxScaler().fit(frame[FEATURES])