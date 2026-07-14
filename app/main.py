from fastapi import FastAPI

from . import predictor
from .schemas import HealthResponse, ModelInfoResponse, PredictionResponse, WineFeatures

app = FastAPI(title="Wine Quality Prediction API", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.post("/predict", response_model=PredictionResponse)
def predict(features: WineFeatures):
    return predictor.predict(features)


@app.get("/model-info", response_model=ModelInfoResponse)
def model_info():
    return predictor.get_metadata()
