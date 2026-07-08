from app import predictor
from app.schemas import WineFeatures, PredictionResponse, ModelInfoResponse


def test_predict_returns_valid_response(sample_payload):
    features = WineFeatures(**sample_payload)

    result = predictor.predict(features)

    assert isinstance(result, PredictionResponse)
    assert isinstance(result.quality, int)
    assert isinstance(result.probability, float)
    assert 0 <= result.probability <= 1


def test_get_metadata():
    result = predictor.get_metadata()

    assert isinstance(result, ModelInfoResponse)
    assert isinstance(result.accuracy, float)
    assert isinstance(result.feature_names, list)
    assert isinstance(result.trained_at, str)
    assert isinstance(result.model_params, dict)
    assert len(result.feature_names) == 11