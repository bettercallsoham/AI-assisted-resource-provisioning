import os
import pickle
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestRegressor

from preprocessing import FEATURES, load_metrics, make_sequences

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)
app = FastAPI(title="AI Provisioning ML Service")


class WorkloadRequest(BaseModel):
    history: list[float] = Field(min_length=2)


class ResourceRequest(BaseModel):
    predicted_request_rate: float
    current_request_rate: float
    cpu_utilization: float
    memory_utilization: float
    network_throughput: float
    response_latency: float


def resource_features(request: ResourceRequest) -> np.ndarray:
    return np.array([[request.predicted_request_rate, request.current_request_rate, request.cpu_utilization, request.memory_utilization, request.network_throughput, request.response_latency]])


def load_rf(resource: str):
    path = MODEL_DIR / f"rf_{resource}.pkl"
    if not path.exists():
        raise HTTPException(503, "Random Forest models are not trained. Run POST /train/random-forest.")
    with path.open("rb") as handle:
        return pickle.load(handle)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "models": [path.name for path in MODEL_DIR.iterdir()]}


@app.post("/predict/workload")
def predict_workload(request: WorkloadRequest) -> dict:
    model_path = MODEL_DIR / "lstm_model.keras"
    if model_path.exists():
        try:
            from tensorflow import keras
            scaler = np.load(MODEL_DIR / "lstm_scaler.npy")
            model = keras.models.load_model(model_path)
            values = np.array(request.history, dtype=float)
            scaled = (values - scaler[0]) / (scaler[1] - scaler[0] or 1)
            window = int(model.input_shape[1])
            prediction = model.predict(scaled[-window:].reshape(1, window, 1), verbose=0)[0][0]
            prediction = prediction * (scaler[1] - scaler[0]) + scaler[0]
        except Exception as error:
            raise HTTPException(500, f"Unable to load LSTM model: {error}") from error
    else:
        if len(request.history) < 3:
            raise HTTPException(503, "LSTM model is not trained. Run POST /train/lstm.")
        prediction = request.history[-1] + (request.history[-1] - request.history[-2])
    return {"predicted_request_rate": round(max(0, float(prediction)), 3), "model": "lstm" if model_path.exists() else "trend-baseline"}


@app.post("/predict/resources")
def predict_resources(request: ResourceRequest) -> dict:
    features = resource_features(request)
    return {f"predicted_{resource}": round(max(0, float(load_rf(resource).predict(features)[0])), 4) for resource in ("cpu", "memory", "network")}


@app.post("/explain/resources")
def explain_resources(request: ResourceRequest) -> dict:
    try:
        import shap
    except ImportError as error:
        raise HTTPException(503, "Install SHAP to enable explanations") from error
    features = resource_features(request)
    output = {}
    for resource in ("cpu", "memory", "network"):
        model = load_rf(resource)
        explanation = shap.TreeExplainer(model)(features)
        values = explanation.values[0]
        output[resource] = {"prediction": float(model.predict(features)[0]), "features": [{"name": name, "contribution": round(float(value), 5)} for name, value in zip(["predicted_request_rate", "current_request_rate", *FEATURES[1:]], values)]}
    return output


@app.post("/train/random-forest")
def train_random_forest(path: str = os.getenv("METRICS_DATA", str(ROOT / "data" / "sample_metrics.csv"))) -> dict:
    frame = load_metrics(path)
    values = frame[FEATURES].to_numpy()
    x = np.column_stack([values[:-1, 0], values[:-1, :]])
    targets = {"cpu": values[1:, 1], "memory": values[1:, 2], "network": values[1:, 3]}
    for resource, target in targets.items():
        model = RandomForestRegressor(n_estimators=80, random_state=42, min_samples_leaf=1).fit(x, target)
        with (MODEL_DIR / f"rf_{resource}.pkl").open("wb") as handle:
            pickle.dump(model, handle)
    return {"status": "trained", "rows": len(x), "models": ["cpu", "memory", "network"]}


@app.post("/train/lstm")
def train_lstm(path: str = os.getenv("METRICS_DATA", str(ROOT / "data" / "sample_metrics.csv")), epochs: int = 20) -> dict:
    try:
        from tensorflow import keras
    except ImportError as error:
        raise HTTPException(503, "TensorFlow is required for LSTM training") from error
    frame = load_metrics(path)
    series = frame["request_rate"].to_numpy(dtype=float)
    window = min(5, len(series) - 1)
    sequences, targets = make_sequences(series, window)
    low, high = float(series.min()), float(series.max())
    scaled = [(np.array(sequence) - low) / (high - low or 1) for sequence in sequences]
    y = (np.array(targets) - low) / (high - low or 1)
    model = keras.Sequential([keras.layers.Input((window, 1)), keras.layers.LSTM(16), keras.layers.Dense(1)])
    model.compile(optimizer="adam", loss="mse")
    model.fit(np.array(scaled)[..., None], y, epochs=epochs, verbose=0)
    model.save(MODEL_DIR / "lstm_model.keras")
    np.save(MODEL_DIR / "lstm_scaler.npy", np.array([low, high]))
    return {"status": "trained", "rows": len(sequences), "epochs": epochs}