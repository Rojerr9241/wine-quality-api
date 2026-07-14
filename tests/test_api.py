def test_health(client):
    response = client.get("/health")
    # status_code first: a failure here is clearer than a KeyError from .json() on an error body
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_predict_valid_payload(client, sample_payload):
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["quality"], int)
    assert isinstance(body["probability"], float)
    assert 0 <= body["probability"] <= 1


def test_predict_invalid_payload(client, sample_payload):
    invalid_payload = sample_payload.copy()
    del invalid_payload["alcohol"]

    response = client.post("/predict", json=invalid_payload)
    assert response.status_code == 422


def test_model_info(client):
    response = client.get("/model-info")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["accuracy"], float)
    assert isinstance(body["feature_names"], list)
    assert isinstance(body["trained_at"], str)
    assert isinstance(body["model_params"], dict)
    assert len(body["feature_names"]) == 11
