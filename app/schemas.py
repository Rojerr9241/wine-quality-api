from pydantic import BaseModel, Field


# Request schema — validated automatically by FastAPI before reaching endpoint logic
class WineFeatures(BaseModel):
    fixed_acidity: float = Field(..., description="Fixed acidity (g/dm³)", example=7.4)
    volatile_acidity: float = Field(..., description="Volatile acidity (g/dm³)", example=0.7)
    citric_acid: float = Field(..., description="Citric acid (g/dm³)", example=0.0)
    residual_sugar: float = Field(..., description="Residual sugar (g/dm³)", example=1.9)
    chlorides: float = Field(..., description="Chlorides / sodium chloride (g/dm³)", example=0.076)
    free_sulfur_dioxide: float = Field(..., description="Free sulfur dioxide (mg/dm³)", example=11.0)
    total_sulfur_dioxide: float = Field(..., description="Total sulfur dioxide (mg/dm³)", example=34.0)
    density: float = Field(..., description="Density (g/cm³)", example=0.9978)
    ph: float = Field(..., ge=0, le=14, description="pH level (0–14 scale)", example=3.51)
    sulphates: float = Field(..., description="Sulphates (g/dm³)", example=0.56)
    alcohol: float = Field(..., ge=0, le=100, description="Alcohol content (% volume)", example=9.4)


# Response schemas
class PredictionResponse(BaseModel):
    quality: int = Field(..., description="Predicted wine quality (3–8)", example=6)
    probability: float = Field(..., description="Model confidence for the predicted class (0–1)", example=0.82)


class HealthResponse(BaseModel):
    status: str = Field(..., example="ok")


class ModelInfoResponse(BaseModel):
    accuracy: float
    feature_names: list[str]
    trained_at: str
    model_params: dict