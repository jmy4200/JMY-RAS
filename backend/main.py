from datetime import datetime, timezone
import platform
import socket

import psutil
from fastapi import FastAPI

app = FastAPI(
    title="JMY Remote Access System",
    description=(
        "Early-stage, consent-based remote administration "
        "and digital forensics platform."
    ),
    version="0.1.0",
)


@app.get("/", tags=["status"])
def home():
    return {
        "system": "JMY-RAS",
        "version": app.version,
        "status": "running",
        "notice": "Development scaffold; remote-control features are not enabled.",
    }


@app.get("/api/health", tags=["status"])
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


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
