from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["system"] == "JMY-RAS"


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_system_info():
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "operating_system" in data
    assert "memory" in data
