from datetime import datetime, timezone
import os
import json
import platform
import socket
from pathlib import Path
from typing import Literal

import psutil
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from .db import init_db, connect
from .network import get_lan_addresses
from .security import (
    create_pairing_code,
    pair_device,
    authenticate_token,
    revoke_device,
    check_pairing_rate_limit,
)
from .host_agent_client import fetch_host_agent, HostAgentUnavailable
from .owner_auth import (
    create_owner_session,
    authenticate_owner_session,
    revoke_owner_session,
    consume_owner_login_attempt,
    clear_owner_login_attempts,
)
from .owner_password import verify_password

app = FastAPI(
    title="JMY Remote Access System",
    description="Consent-based remote administration and digital forensics development platform.",
    version="0.4.2",
)


@app.on_event("startup")
def startup():
    init_db()


class PairRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    device_name: str = Field(min_length=1, max_length=80)
    platform: str = Field(min_length=1, max_length=80)


class OwnerLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class OfflineEvent(BaseModel):
    event_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    event_type: Literal["operator_note"] = "operator_note"
    note: str = Field(min_length=1, max_length=500)
    client_created_at: str = Field(min_length=1, max_length=40)


class OfflineSyncBatch(BaseModel):
    events: list[OfflineEvent] = Field(min_length=1, max_length=50)


def current_device(authorization: str | None = Header(default=None)):
    parts = authorization.strip().split() if authorization else []
    if len(parts) != 2 or parts[0].casefold() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required")

    device = authenticate_token(parts[1])
    if not device:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return device


def current_owner(authorization: str | None = Header(default=None)):
    parts = authorization.strip().split() if authorization else []
    if len(parts) != 2 or parts[0].casefold() != "bearer":
        raise HTTPException(status_code=401, detail="Owner bearer token required")

    session = authenticate_owner_session(parts[1])
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired owner session")
    return session


@app.get("/", tags=["status"])
def home():
    return {
        "system": "JMY-RAS",
        "version": app.version,
        "status": "running",
        "notice": "Offline-first dashboard, LAN pairing and queued operator notes. Remote-control functions are not enabled.",
    }


@app.get("/api/health", tags=["status"])
def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/system/info", tags=["inventory"])
def system_info():
    memory = psutil.virtual_memory()
    return {
        "hostname": socket.gethostname(),
        "operating_system": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_usage_percent": psutil.cpu_percent(interval=0.2),
        "memory": {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_percent": memory.percent,
        },
    }


@app.get("/api/network/lan-info", tags=["network"])
def lan_info():
    """Expose connection instructions, not credentials or pairing secrets."""
    return {
        "hostname": socket.gethostname(),
        "api_port": 8000,
        "addresses": get_lan_addresses(),
        "transport": "HTTP (development only; use encrypted transport before production)",
    }


@app.get("/api/host-agent/health", tags=["host agent"])
def host_agent_health(device=Depends(current_device)):
    """Return authenticated health status from the configured local host agent."""
    try:
        return fetch_host_agent("/health")
    except HostAgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/host-agent/host", tags=["host agent"])
def host_agent_inventory(device=Depends(current_device)):
    """Return read-only host inventory from the configured Linux host agent."""
    try:
        return fetch_host_agent("/v1/host")
    except HostAgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/pairing/code", tags=["pairing"])
def new_pairing_code(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Generate pairing codes locally on the host computer")
    return {"pairing_code": create_pairing_code(), "expires_in_seconds": 300}


@app.post("/api/pairing/claim", tags=["pairing"])
def claim_pairing(payload: PairRequest, request: Request, response: Response):
    client_host = request.client.host if request.client else "unknown"
    limited, retry_after = check_pairing_rate_limit(client_host)
    if limited:
        raise HTTPException(
            status_code=429,
            detail="Too many pairing attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    result = pair_device(payload.code, payload.device_name, payload.platform)
    if not result:
        raise HTTPException(status_code=400, detail="Pairing code invalid, expired, or already used")

    # Pairing responses contain a bearer credential and must not be cached.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return result


@app.post("/api/owner/login", tags=["owner"])
def owner_login(payload: OwnerLoginRequest, request: Request, response: Response):
    password_hash = os.getenv("JMY_OWNER_PASSWORD_HASH", "").strip()
    if not password_hash:
        raise HTTPException(
            status_code=503,
            detail="Owner authentication is not configured on this server",
        )

    client_host = request.client.host if request.client else "unknown"
    limited, retry_after = consume_owner_login_attempt(client_host)
    if limited:
        raise HTTPException(
            status_code=429,
            detail="Too many owner login failures. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid owner credentials")

    clear_owner_login_attempts(client_host)
    token, expires_at = create_owner_session()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "expires_in": 8 * 60 * 60,
    }


@app.get("/api/owner/me", tags=["owner"])
def owner_me(owner=Depends(current_owner)):
    return {"session_id": owner["id"], "expires_at": owner["expires_at"]}


@app.post("/api/owner/logout", tags=["owner"])
def owner_logout(owner=Depends(current_owner)):
    revoke_owner_session(owner["id"])
    return {"logged_out": True}


@app.get("/api/owner/devices", tags=["owner"])
def owner_list_devices(owner=Depends(current_owner)):
    with connect() as conn:
        rows = conn.execute(
            """SELECT id,name,platform,created_at,last_seen,is_active
               FROM devices ORDER BY created_at DESC"""
        ).fetchall()
    return {"devices": [dict(row) for row in rows]}


@app.post("/api/owner/devices/{device_id}/revoke", tags=["owner"])
def owner_revoke_device(device_id: str, owner=Depends(current_owner)):
    if not revoke_device(device_id, actor="owner", actor_id=owner["id"]):
        raise HTTPException(status_code=404, detail="Device not found or already revoked")
    return {"device_id": device_id, "revoked": True}


@app.get("/api/owner/audit/recent", tags=["owner"])
def owner_recent_audit(limit: int = 100, owner=Depends(current_owner)):
    limit = max(1, min(limit, 500))
    with connect() as conn:
        rows = conn.execute(
            """SELECT event,device_id,details,timestamp
               FROM audit_events ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


@app.get("/api/devices/me", tags=["devices"])
def my_device(device=Depends(current_device)):
    return device


@app.post("/api/devices/me/revoke", tags=["devices"])
def revoke_my_device(device=Depends(current_device)):
    """Revoke only the credential used for this request; retain its audit history."""
    if not revoke_device(device["id"]):
        raise HTTPException(status_code=409, detail="Device is already revoked")
    return {"device_id": device["id"], "revoked": True}


@app.get("/api/devices", tags=["devices"])
def list_devices(device=Depends(current_device)):
    """Return only the authenticated device; cross-device administration is not enabled."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT id,name,platform,created_at,last_seen
               FROM devices WHERE id=? AND is_active=1""",
            (device["id"],),
        ).fetchall()
    return {"devices": [dict(row) for row in rows]}


@app.post("/api/sync/events", tags=["offline sync"])
def sync_offline_events(batch: OfflineSyncBatch, device=Depends(current_device)):
    """Accept idempotent, consented operator notes queued by the offline dashboard."""
    received_at = datetime.now(timezone.utc).isoformat()
    accepted = 0
    duplicates = 0
    with connect() as conn:
        for event in batch.events:
            exists = conn.execute(
                "SELECT 1 FROM sync_events WHERE event_id=?", (event.event_id,)
            ).fetchone()
            if exists:
                duplicates += 1
                continue
            conn.execute(
                """INSERT INTO sync_events
                   (event_id,device_id,event_type,note,client_created_at,received_at)
                   VALUES(?,?,?,?,?,?)""",
                (event.event_id, device["id"], event.event_type, event.note,
                 event.client_created_at, received_at),
            )
            accepted += 1
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,?,?,?)",
            ("offline_events_synced", device["id"],
             json.dumps({"accepted": accepted, "duplicates": duplicates}), received_at),
        )
    return {"accepted": accepted, "duplicates": duplicates, "received_at": received_at}


@app.get("/api/sync/events", tags=["offline sync"])
def list_synced_events(device=Depends(current_device)):
    with connect() as conn:
        rows = conn.execute(
            """SELECT event_id,event_type,note,client_created_at,received_at
               FROM sync_events WHERE device_id=? ORDER BY received_at DESC LIMIT 100""",
            (device["id"],),
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


@app.get("/api/audit/recent", tags=["audit"])
def recent_audit(device=Depends(current_device)):
    """Expose only this device's audit events, not other devices' activity."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT event,device_id,details,timestamp
               FROM audit_events WHERE device_id=? ORDER BY id DESC LIMIT 100""",
            (device["id"],),
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dashboard"
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
