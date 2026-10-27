import os
from pathlib import Path

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from preprocessing import FEATURES
from prediction.lstm_predictor import LSTMPredictor
from prediction.resource_predictor import ResourcePredictor
from training.train_random_forest import train as train_random_forest_models
from training.train_lstm import train as train_lstm_model

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)
app = FastAPI(title="AI Provisioning ML Service")


class WorkloadRequest(BaseModel):
    history: list[float] = Field(min_length=12)


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
    path = MODEL_DIR / f"rf_{resource}.joblib"
    if not path.exists():
        raise HTTPException(503, "Random Forest models are not trained. Run POST /train/random-forest.")
    return joblib.load(path)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "models": [path.name for path in MODEL_DIR.iterdir()]}


@app.post("/predict/workload")
def predict_workload(request: WorkloadRequest) -> dict:
    model_path = MODEL_DIR / "lstm_model.keras"
    scaler_path = MODEL_DIR / "lstm_scaler.joblib"
    if not model_path.exists() or not scaler_path.exists():
        raise HTTPException(503, "LSTM model is not trained. Run the LSTM training script.")
    try:
        prediction = LSTMPredictor(model_path, scaler_path).predict(request.history)
    except Exception as error:
        raise HTTPException(500, f"Unable to predict with LSTM model: {error}") from error
    return {"predicted_request_rate": round(max(0, prediction), 3), "model": "lstm"}


@app.post("/predict/resources")
def predict_resources(request: ResourceRequest) -> dict:
    try:
        predictions = ResourcePredictor().predict(**request.model_dump())
    except FileNotFoundError as error:
        raise HTTPException(503, "Random Forest models are not trained. Run POST /train/random-forest.") from error
    except Exception as error:
        raise HTTPException(500, f"Unable to predict resource demand: {error}") from error
    return {name: round(value, 4) for name, value in predictions.items()}


@app.post("/explain/resources")
def explain_resources(request: ResourceRequest) -> dict:
    try:
        predictor = ResourcePredictor()
        features = resource_features(request)
        return {resource: predictor.explain(resource, features) for resource in ("cpu", "memory", "network")}
    except FileNotFoundError as error:
        raise HTTPException(503, "Random Forest models are not trained. Run POST /train/random-forest.") from error
    except Exception as error:
        raise HTTPException(500, f"Unable to explain resource predictions: {error}") from error


@app.post("/explain/resources/{resource}")
def explain_resource(resource: str, request: ResourceRequest) -> dict:
    if resource not in ("cpu", "memory", "network"):
        raise HTTPException(404, "Resource must be cpu, memory, or network")
    try:
        return ResourcePredictor().explain(resource, resource_features(request))
    except FileNotFoundError as error:
        raise HTTPException(503, "Random Forest models are not trained. Run POST /train/random-forest.") from error
    except Exception as error:
        raise HTTPException(500, f"Unable to explain {resource} prediction: {error}") from error


@app.post("/train/random-forest")
def train_random_forest(path: str = os.getenv("METRICS_DATA", str(ROOT / "data" / "final_dataset.csv"))) -> dict:
    try:
        metrics = train_random_forest_models(Path(path))
    except Exception as error:
        raise HTTPException(500, f"Unable to train Random Forest models: {error}") from error
    return {"status": "trained", "metrics": metrics}


@app.post("/train/lstm")
def train_lstm(path: str = os.getenv("METRICS_DATA", str(ROOT / "data" / "final_dataset.csv")), epochs: int = 30) -> dict:
    try:
        metrics = train_lstm_model(
            Path(path),
            MODEL_DIR / "lstm_model.keras",
            MODEL_DIR / "lstm_scaler.joblib",
            MODEL_DIR / "lstm_metrics.json",
            window=12,
            epochs=epochs,
            batch_size=32,
        )
    except Exception as error:
        raise HTTPException(500, f"Unable to train LSTM: {error}") from error
    return {"status": "trained", **metrics}
