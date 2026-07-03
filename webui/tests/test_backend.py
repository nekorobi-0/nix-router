from fastapi.testclient import TestClient

from backend import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_status() -> None:
    response = client.get("/api/status")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body["hostname"], str)
    assert isinstance(body["uptimeSeconds"], int)
    assert isinstance(body["interfaces"], list)


def test_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Nix Router" in response.text
