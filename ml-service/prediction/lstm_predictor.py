from pathlib import Path

import joblib
import numpy as np
from tensorflow import keras


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "lstm_model.keras"
SCALER_PATH = ROOT / "models" / "lstm_scaler.joblib"


class LSTMPredictor:
    def __init__(self, model_path: str | Path = MODEL_PATH, scaler_path: str | Path = SCALER_PATH):
        self.model = keras.models.load_model(model_path)
        self.scaler = joblib.load(scaler_path)
        self.window = int(self.model.input_shape[1])

    def predict(self, history: list[float]) -> float:
        values = np.asarray(history, dtype=float)
        if values.ndim != 1 or len(values) < self.window:
            raise ValueError(f"history must contain at least {self.window} request-rate values")
        scaled = self.scaler.transform(values[-self.window:].reshape(-1, 1))
        predicted_scaled = self.model.predict(scaled.reshape(1, self.window, 1), verbose=0)
        return float(self.scaler.inverse_transform(predicted_scaled)[0, 0])


def predict_request_rate(history: list[float]) -> float:
    return LSTMPredictor().predict(history)