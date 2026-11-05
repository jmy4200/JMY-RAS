from datetime import datetime, timezone
import platform
import socket

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .db import init_db, connect
from .network import get_lan_addresses
from .security import create_pairing_code, pair_device, authenticate_token

app = FastAPI(
    title="JMY Remote Access System",
    description="Consent-based remote administration and digital forensics development platform.",
    version="0.3.0",
)


@app.on_event("startup")
def startup():
    init_db()


class PairRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    device_name: str = Field(min_length=1, max_length=80)
    platform: str = Field(min_length=1, max_length=80)


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
        "notice": "LAN discovery and device pairing foundation only. Remote-control functions are not enabled.",
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
    # Pairing codes may only be created locally by the computer owner.
    # A remote LAN client can claim a code, but cannot mint new codes.
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


@app.get("/api/audit/recent", tags=["audit"])
def recent_audit(device=Depends(current_device)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT event,device_id,details,timestamp FROM audit_events ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return {"events": [dict(row) for row in rows]}
