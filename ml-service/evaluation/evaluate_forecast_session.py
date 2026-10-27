"""Score the unchanged saved LSTM on timestamp-matched five-second rows."""

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_rows(path: Path) -> list[tuple[datetime, float]]:
    with path.open(newline="", encoding="utf-8") as source:
        raw = list(csv.DictReader(source))
    rows = [(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
             float(row["request_rate"])) for row in raw]
    if any(not math.isfinite(value) or value < 0 for _, value in rows):
        raise ValueError("Request rates must be finite and non-negative")
    if any((right[0] - left[0]).total_seconds() <= 0 for left, right in zip(rows, rows[1:])):
        raise ValueError("Timestamps must increase strictly")
    return rows


def matched_windows(rows: list[tuple[datetime, float]], window: int,
                    tolerance_seconds: float = 0.5) -> list[int]:
    """Return target indices with 12 preceding measurements spaced about 5 s apart."""
    return [index for index in range(window, len(rows))
            if all(abs((rows[position][0] - rows[position - 1][0]).total_seconds() - 5)
                   <= tolerance_seconds for position in range(index - window + 1, index + 1))]


def evaluate(path: Path) -> dict:
    import numpy as np
    from prediction.lstm_predictor import LSTMPredictor

    rows = load_rows(path)
    predictor = LSTMPredictor()
    indices = matched_windows(rows, predictor.window)
    if not indices:
        raise ValueError("No timestamp-matched forecast targets are available")
    histories = np.asarray([[rows[position][1] for position in range(index - predictor.window, index)]
                            for index in indices])
    forecast = np.maximum(0, predictor.predict_many(histories))
    actual = np.asarray([rows[index][1] for index in indices])
    trailing = histories.mean(axis=1)
    changes = np.abs(actual - histories[:, -1])
    abrupt = changes >= 3
    minimum = float(predictor.scaler.data_min_[0])
    maximum = float(predictor.scaler.data_max_[0])
    return {
        "dataset": str(path), "rows": len(rows), "matched_targets": len(indices),
        "window": predictor.window, "horizon_seconds": 5,
        "first_target": rows[indices[0]][0].isoformat(),
        "last_target": rows[indices[-1]][0].isoformat(),
        "request_rate_unit": "req/s",
        "observed": {"median": float(statistics.median(value for _, value in rows)),
                     "min": min(value for _, value in rows), "max": max(value for _, value in rows)},
        "training_scaler_range": {"min": minimum, "max": maximum},
        "input_values_below_training_min": int((histories < minimum).sum()),
        "input_values_above_training_max": int((histories > maximum).sum()),
        "input_values": int(histories.size),
        "mae_req_per_second": {"saved_lstm": float(np.mean(np.abs(forecast - actual))),
                               "trailing_12_mean": float(np.mean(np.abs(trailing - actual))),
                               "persistence": float(np.mean(np.abs(histories[:, -1] - actual)))},
        "mean_error_forecast_minus_actual": float(np.mean(forecast - actual)),
        "abrupt_change_at_least_3_req_per_second": {
            "targets": int(abrupt.sum()),
            "lstm_mae": float(np.mean(np.abs(forecast[abrupt] - actual[abrupt]))) if abrupt.any() else None,
            "persistence_mae": float(np.mean(changes[abrupt])) if abrupt.any() else None,
        },
        "first_pairs": [{"origin": rows[index - 1][0].isoformat(),
                         "target": rows[index][0].isoformat(),
                         "actual": float(actual[offset]), "lstm": float(forecast[offset])}
                        for offset, index in enumerate(indices[:3])],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), indent=2))
