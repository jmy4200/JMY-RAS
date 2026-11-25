import pytest
import uuid
from fastapi.testclient import TestClient

from backend import db
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
    assert pair_response.headers["cache-control"] == "no-store"
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


@pytest.mark.parametrize(
    "authorization",
    ["Basic abc", "Bearer", "Bearer invalid-token extra", "bearer invalid-token"],
)
def test_protected_endpoint_rejects_malformed_or_invalid_token(client, authorization):
    response = client.get(
        "/api/devices/me",
        headers={"Authorization": authorization},
    )
    assert response.status_code == 401


def test_device_can_revoke_only_its_own_access_token(client):
    def pair_device(device_name):
        code_response = client.post("/api/pairing/code")
        assert code_response.status_code == 200
        claim_response = client.post(
            "/api/pairing/claim",
            json={
                "code": code_response.json()["pairing_code"],
                "device_name": device_name,
                "platform": "Linux",
            },
        )
        assert claim_response.status_code == 200
        return claim_response.json()

    first_device = pair_device("first-device")
    second_device = pair_device("second-device")
    first_headers = {"Authorization": f"Bearer {first_device['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second_device['access_token']}"}

    revoked = client.post("/api/devices/me/revoke", headers=first_headers)
    assert revoked.status_code == 200
    assert revoked.json() == {
        "device_id": first_device["device_id"],
        "revoked": True,
    }

    assert client.get("/api/devices/me", headers=first_headers).status_code == 401
    assert client.get("/api/devices/me", headers=second_headers).status_code == 200

    # The second device must not learn the first device's audit history.
    audit = client.get("/api/audit/recent", headers=second_headers)
    assert audit.status_code == 200
    assert all(event["device_id"] == second_device["device_id"] for event in audit.json()["events"])


def test_device_inventory_and_audit_are_isolated(client):
    def pair_device(device_name):
        code = client.post("/api/pairing/code")
        assert code.status_code == 200
        claim = client.post(
            "/api/pairing/claim",
            json={
                "code": code.json()["pairing_code"],
                "device_name": device_name,
                "platform": "Linux",
            },
        )
        assert claim.status_code == 200
        return claim.json()

    first = pair_device("privacy-test-one")
    second = pair_device("privacy-test-two")
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    first_devices = client.get("/api/devices", headers=first_headers).json()["devices"]
    second_devices = client.get("/api/devices", headers=second_headers).json()["devices"]
    assert [item["id"] for item in first_devices] == [first["device_id"]]
    assert [item["id"] for item in second_devices] == [second["device_id"]]

    first_audit = client.get("/api/audit/recent", headers=first_headers).json()["events"]
    second_audit = client.get("/api/audit/recent", headers=second_headers).json()["events"]
    assert all(item["device_id"] == first["device_id"] for item in first_audit)
    assert all(item["device_id"] == second["device_id"] for item in second_audit)


def test_pairing_claim_is_rate_limited_per_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "rate-limit.sqlite3")
    with TestClient(app, client=("192.0.2.77", 50000)) as remote_client:
        payload = {
            "code": "000000",
            "device_name": "rate-limit-test",
            "platform": "Linux",
        }
        responses = [
            remote_client.post("/api/pairing/claim", json=payload)
            for _ in range(10)
        ]
        assert all(response.status_code == 400 for response in responses)

        limited = remote_client.post("/api/pairing/claim", json=payload)
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0


def test_dashboard_is_served(client):
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "JMY-RAS" in response.text
    assert 'app.js?v=0.5.0' in response.text


def test_dashboard_script_contains_session_token_restore(client):
    response = client.get("/dashboard/assets/app.js")
    assert response.status_code == 200
    assert "sessionStorage.getItem(TOKEN_KEY)" in response.text
    assert 'Authorization: "Bearer " + token' in response.text
