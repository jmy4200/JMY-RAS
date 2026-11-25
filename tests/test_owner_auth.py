import json

from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from backend.owner_password import hash_password, verify_password
from backend import owner_auth


OWNER_PASSWORD = "JMY-RAS-Owner-Password-2026!"


def test_owner_password_hash_is_salted_and_verifiable():
    first = hash_password(OWNER_PASSWORD, iterations=100_000)
    second = hash_password(OWNER_PASSWORD, iterations=100_000)

    assert first != second
    assert verify_password(OWNER_PASSWORD, first)
    assert not verify_password("incorrect password", first)
    assert not verify_password(OWNER_PASSWORD, "not-a-valid-hash")


def test_owner_can_list_revoke_devices_and_review_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "owner.sqlite3")
    monkeypatch.setenv(
        "JMY_OWNER_PASSWORD_HASH",
        hash_password(OWNER_PASSWORD, iterations=100_000),
    )

    with TestClient(app) as client:
        def pair(name):
            code = client.post("/api/pairing/code")
            assert code.status_code == 200
            claim = client.post(
                "/api/pairing/claim",
                json={
                    "code": code.json()["pairing_code"],
                    "device_name": name,
                    "platform": "Linux",
                },
            )
            assert claim.status_code == 200
            return claim.json()

        first = pair("owner-test-one")
        second = pair("owner-test-two")

        login = client.post(
            "/api/owner/login",
            json={"password": OWNER_PASSWORD},
        )
        assert login.status_code == 200
        assert login.headers["cache-control"] == "no-store"
        assert login.json()["expires_in"] == 8 * 60 * 60

        owner_headers = {
            "Authorization": "Bearer " + login.json()["access_token"]
        }
        first_headers = {"Authorization": "Bearer " + first["access_token"]}
        second_headers = {"Authorization": "Bearer " + second["access_token"]}

        assert client.get("/api/owner/me", headers=owner_headers).status_code == 200
        assert client.get("/api/owner/devices", headers=first_headers).status_code == 401

        inventory = client.get("/api/owner/devices", headers=owner_headers)
        assert inventory.status_code == 200
        assert {item["id"] for item in inventory.json()["devices"]} >= {
            first["device_id"],
            second["device_id"],
        }

        revoked = client.post(
            "/api/owner/devices/" + second["device_id"] + "/revoke",
            headers=owner_headers,
        )
        assert revoked.status_code == 200
        assert client.get("/api/devices/me", headers=second_headers).status_code == 401
        assert client.get("/api/devices/me", headers=first_headers).status_code == 200

        inventory = client.get("/api/owner/devices", headers=owner_headers).json()
        revoked_record = next(
            item for item in inventory["devices"] if item["id"] == second["device_id"]
        )
        assert revoked_record["is_active"] == 0

        audit = client.get("/api/owner/audit/recent?limit=50", headers=owner_headers)
        assert audit.status_code == 200
        revocation_event = next(
            item for item in audit.json()["events"]
            if item["event"] == "device_revoked"
            and item["device_id"] == second["device_id"]
        )
        details = json.loads(revocation_event["details"])
        assert details["actor"] == "owner"
        audit_events = [item["event"] for item in audit.json()["events"]]
        assert "owner_login" in audit_events
        assert "owner_devices_listed" in audit_events
        assert "owner_audit_viewed" in audit_events

        logout = client.post("/api/owner/logout", headers=owner_headers)
        assert logout.status_code == 200
        assert client.get("/api/owner/devices", headers=owner_headers).status_code == 401


def test_owner_login_is_disabled_without_configured_password(monkeypatch):
    monkeypatch.delenv("JMY_OWNER_PASSWORD_HASH", raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/owner/login",
            json={"password": OWNER_PASSWORD},
        )
    assert response.status_code == 503


def test_owner_login_throttles_repeated_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "owner-limit.sqlite3")
    monkeypatch.setenv(
        "JMY_OWNER_PASSWORD_HASH",
        hash_password(OWNER_PASSWORD, iterations=100_000),
    )

    with TestClient(app, client=("192.0.2.99", 50000)) as client:
        for _ in range(5):
            response = client.post(
                "/api/owner/login",
                json={"password": "incorrect owner password"},
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/owner/login",
            json={"password": OWNER_PASSWORD},
        )
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0



def test_owner_session_expires_after_its_ttl(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "owner-expiry.sqlite3")
    db.init_db()
    fixed_now = 1_800_000_000
    monkeypatch.setattr(owner_auth.time, "time", lambda: fixed_now)

    token, expires_at = owner_auth.create_owner_session()
    assert owner_auth.authenticate_owner_session(token) is not None

    monkeypatch.setattr(owner_auth.time, "time", lambda: expires_at + 1)
    assert owner_auth.authenticate_owner_session(token) is None
