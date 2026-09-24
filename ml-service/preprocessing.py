from pathlib import Path

import pandas as pd
from sklearn.preprocessing import MinMaxScaler

FEATURES = ["request_rate", "cpu_utilization", "memory_utilization", "network_throughput", "response_latency"]


def load_metrics(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    frame[FEATURES] = frame[FEATURES].apply(pd.to_numeric, errors="coerce").interpolate().ffill().bfill()
    for feature in FEATURES:
        low, high = frame[feature].quantile(0.01), frame[feature].quantile(0.99)
        frame[feature] = frame[feature].clip(lower=low, upper=high)
    return frame


def make_sequences(values, window: int = 5):
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