from datetime import datetime, timezone
import json
import platform
import socket
from pathlib import Path
from typing import Literal

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import init_db, connect
from .network import get_lan_addresses
from .security import create_pairing_code, pair_device, authenticate_token

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


class OfflineEvent(BaseModel):
    event_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    event_type: Literal["operator_note"] = "operator_note"
    note: str = Field(min_length=1, max_length=500)
    client_created_at: str = Field(min_length=1, max_length=40)


class OfflineSyncBatch(BaseModel):
    events: list[OfflineEvent] = Field(min_length=1, max_length=50)


def current_device(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split(" ", 1)[1].strip()
    device = authenticate_token(token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return device


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


@app.post("/api/pairing/code", tags=["pairing"])
def new_pairing_code(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Generate pairing codes locally on the host computer")
    return {"pairing_code": create_pairing_code(), "expires_in_seconds": 300}


@app.post("/api/pairing/claim", tags=["pairing"])
def claim_pairing(request: PairRequest):
    result = pair_device(request.code, request.device_name, request.platform)
    if not result:
        raise HTTPException(status_code=400, detail="Pairing code invalid, expired, or already used")
    return result


@app.get("/api/devices/me", tags=["devices"])
def my_device(device=Depends(current_device)):
    return device


@app.get("/api/devices", tags=["devices"])
def list_devices(device=Depends(current_device)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,name,platform,created_at,last_seen FROM devices ORDER BY created_at"
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
    with connect() as conn:
        rows = conn.execute(
            "SELECT event,device_id,details,timestamp FROM audit_events ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dashboard"
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
