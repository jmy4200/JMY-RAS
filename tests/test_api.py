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


def test_pairing_and_authenticated_routes():
    code_response = client.post("/api/pairing/code")
    assert code_response.status_code == 200
    code = code_response.json()["pairing_code"]

    pair_response = client.post("/api/pairing/claim", json={
        "code": code, "device_name": "test-phone", "platform": "Android"
    })
    assert pair_response.status_code == 200
    token = pair_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/devices/me", headers=headers).status_code == 200
    assert client.get("/api/devices", headers=headers).status_code == 200
    assert client.get("/api/audit/recent", headers=headers).status_code == 200

    second_claim = client.post("/api/pairing/claim", json={
        "code": code, "device_name": "another-device", "platform": "Linux"
    })
    assert second_claim.status_code == 400


def test_protected_endpoint_rejects_missing_token():
    assert client.get("/api/devices/me").status_code == 401
