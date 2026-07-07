
def test_health(client):
    response = client.get("/health")
    # status_code first: a failure here is clearer than a KeyError from .json() on an error body
    assert response.status_code == 200
    assert response.json()["status"] == "ok"