import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import MinMaxScaler
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tensorflow import keras

from preprocessing import load_lstm_frame


DEFAULT_DATASET = ROOT / "data" / "final_dataset.csv"
DEFAULT_MODEL = ROOT / "models" / "lstm_model.keras"
DEFAULT_SCALER = ROOT / "models" / "lstm_scaler.joblib"
DEFAULT_METRICS = ROOT / "models" / "lstm_metrics.json"


def split_frame(frame, train_ratio: float = 0.7, validation_ratio: float = 0.15):
    train_end = int(len(frame) * train_ratio)
    validation_end = train_end + int(len(frame) * validation_ratio)
    if train_end == 0 or validation_end >= len(frame):
        raise ValueError("Dataset is too small for the requested chronological split")
    return frame.iloc[:train_end], frame.iloc[train_end:validation_end], frame.iloc[validation_end:]


def sequences_for_segment(history: np.ndarray, segment: np.ndarray, window: int):
    values = np.concatenate([history[-window:], segment])
    sequences = np.array([values[index:index + window] for index in range(len(segment))])
    targets = segment.copy()
    return sequences, targets


def build_model(window: int) -> keras.Model:
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(window, 1)),
            keras.layers.LSTM(32),
            keras.layers.Dense(1),
        ]
    )
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=0.001), loss="mse")
    return model


def train(dataset: Path, model_path: Path, scaler_path: Path, metrics_path: Path, window: int, epochs: int, batch_size: int) -> dict[str, float | int]:
    frame = load_lstm_frame(dataset)
    train_frame, validation_frame, test_frame = split_frame(frame)
    train_values = train_frame["request_rate"].to_numpy(dtype=float)
    validation_values = validation_frame["request_rate"].to_numpy(dtype=float)
    test_values = test_frame["request_rate"].to_numpy(dtype=float)
    if len(train_values) <= window:
        raise ValueError("window must be smaller than the training split")

    scaler = MinMaxScaler()
    train_scaled = scaler.fit_transform(train_values.reshape(-1, 1)).ravel()
    validation_scaled = scaler.transform(validation_values.reshape(-1, 1)).ravel()
    test_scaled = scaler.transform(test_values.reshape(-1, 1)).ravel()
    x_train, y_train = sequences_for_segment(train_scaled[:window], train_scaled[window:], window)
    x_validation, y_validation = sequences_for_segment(train_scaled, validation_scaled, window)
    x_test, y_test = sequences_for_segment(np.concatenate([train_scaled, validation_scaled]), test_scaled, window)

    keras.utils.set_random_seed(42)
    model = build_model(window)
    model.fit(
        x_train[..., None],
        y_train,
        validation_data=(x_validation[..., None], y_validation),
        epochs=epochs,
        batch_size=batch_size,
        verbose=0,
        callbacks=[keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)],
    )
    predicted_scaled = model.predict(x_test[..., None], verbose=0)
    predicted = scaler.inverse_transform(predicted_scaled).ravel()
    metrics = {
        "mae": float(mean_absolute_error(test_values, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(test_values, predicted))),
        "r2": float(r2_score(test_values, predicted)),
        "rows": int(len(frame)),
        "train_rows": int(len(train_frame)),
        "validation_rows": int(len(validation_frame)),
        "test_rows": int(len(test_frame)),
        "window": int(window),
        "epochs": int(epochs),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    joblib.dump(scaler, scaler_path)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train an LSTM for next request-rate prediction")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--scaler", type=Path, default=DEFAULT_SCALER)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--window", type=int, default=12)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    result = train(args.dataset, args.model, args.scaler, args.metrics, args.window, args.epochs, args.batch_size)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()