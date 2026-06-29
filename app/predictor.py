import json
from pathlib import Path

import joblib
import pandas as pd

from .schemas import WineFeatures, PredictionResponse, ModelInfoResponse

MODELS_DIR = Path(__file__).parent.parent / "models"

# Column names as the pipeline expects them (matches training data)
FEATURE_NAMES = [
    "fixed acidity", "volatile acidity", "citric acid", "residual sugar",
    "chlorides", "free sulfur dioxide", "total sulfur dioxide",
    "density", "pH", "sulphates", "alcohol",
]

# Loaded once at import time — avoids reloading on every request
_pipeline = joblib.load(MODELS_DIR / "pipeline.joblib")
_metadata = json.loads((MODELS_DIR / "metadata.json").read_text())


def predict(features: WineFeatures) -> PredictionResponse:
    # model_dump() preserves field definition order, which matches FEATURE_NAMES
    values = list(features.model_dump().values())
    input_df = pd.DataFrame([values], columns=FEATURE_NAMES)

    predicted_quality = _pipeline.predict(input_df)[0]
    predicted_proba = _pipeline.predict_proba(input_df)[0].max()

    return PredictionResponse(
        quality=int(predicted_quality),
        probability=float(predicted_proba),
    )


def get_metadata() -> ModelInfoResponse:
    return ModelInfoResponse(**_metadata)