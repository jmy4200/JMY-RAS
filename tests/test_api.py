import pytest
import uuid
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["system"] == "JMY-RAS"
    assert response.json()["version"] == "0.4.2"


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_system_info(client):
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "operating_system" in data
    assert "memory" in data


def test_lan_info(client):
    response = client.get("/api/network/lan-info")
    assert response.status_code == 200
    data = response.json()
    assert data["api_port"] == 8000
    assert isinstance(data["addresses"], list)


def test_pairing_and_authenticated_routes(client):
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
    sync_body = {"events": [{"event_id": str(uuid.uuid4()), "event_type": "operator_note", "note": "Offline check completed", "client_created_at": "2026-11-05T10:00:00+00:00"}]}
    synced = client.post("/api/sync/events", json=sync_body, headers=headers)
    assert synced.status_code == 200
    assert synced.json()["accepted"] == 1
    duplicate = client.post("/api/sync/events", json=sync_body, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicates"] == 1
    listed = client.get("/api/sync/events", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["events"][0]["note"] == "Offline check completed"

    second_claim = client.post("/api/pairing/claim", json={
        "code": code, "device_name": "another-device", "platform": "Linux"
    })
    assert second_claim.status_code == 400


def test_remote_client_cannot_generate_pairing_code():
    with TestClient(app, client=("192.168.1.50", 50000)) as remote_client:
        response = remote_client.post("/api/pairing/code")
    assert response.status_code == 403


def test_protected_endpoint_rejects_missing_token(client):
    assert client.get("/api/devices/me").status_code == 401
    assert client.post("/api/sync/events", json={"events": []}).status_code == 401


def test_dashboard_is_served(client):
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "JMY-RAS" in response.text
    assert 'app.js?v=0.4.2' in response.text


def test_dashboard_script_contains_session_token_restore(client):
    response = client.get("/dashboard/assets/app.js")
    assert response.status_code == 200
    assert "sessionStorage.getItem(TOKEN_KEY)" in response.text
    assert 'Authorization: "Bearer " + token' in response.text
