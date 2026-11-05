#!/usr/bin/env python3
"""JMY-RAS Linux host agent: read-only inventory over an authenticated private interface.

This first release deliberately does not execute shell commands, capture the screen,
or inject keyboard/mouse input. Bind it only to a trusted VPN interface.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import platform
import secrets
import socket
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil

APP_VERSION = "0.1.0"


def token_path() -> Path:
    configured = os.environ.get("JMY_AGENT_TOKEN_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "jmy-ras" / "agent.token"


def load_or_create_token(path: Path | None = None) -> str:
    """Load a 0600 token, creating it atomically when missing."""
    target = path or token_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        info = target.stat()
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("Agent token path must be a regular file")
        if info.st_mode & 0o077:
            raise RuntimeError(f"Unsafe token permissions on {target}; run chmod 600 on it")
        token = target.read_text(encoding="utf-8").strip()
        if len(token) < 40:
            raise RuntimeError("Agent token file is invalid; remove it and restart the agent")
        return token
    except FileNotFoundError:
        token = secrets.token_urlsafe(48)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        return token


def build_host_info() -> dict:
    memory = psutil.virtual_memory()
    return {
        "agent": "JMY-RAS Linux Host Agent",
        "agent_version": APP_VERSION,
        "hostname": socket.gethostname(),
        "operating_system": platform.system(),
        "distribution": platform.freedesktop_os_release().get("PRETTY_NAME", platform.platform())
        if hasattr(platform, "freedesktop_os_release") else platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "cpu_logical_count": psutil.cpu_count(logical=True),
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
        "memory_total_bytes": memory.total,
        "memory_available_bytes": memory.available,
        "memory_used_percent": memory.percent,
        "capabilities": {
            "host_inventory": True,
            "screen_view": False,
            "keyboard_mouse_control": False,
            "terminal": False,
            "file_transfer": False,
        },
        "security": {
            "authentication": "bearer token",
            "transport": "private VPN interface; VPN encryption required",
            "remote_command_execution": False,
        },
    }


def make_handler(token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "JMY-RAS-Agent"
        sys_version = ""

        def log_message(self, fmt, *args):
            # Keep concise access logs; never log Authorization headers.
            print(f"[JMY-RAS] {self.address_string()} - {fmt % args}")

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return hmac.compare_digest(supplied, expected)

        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path not in {"/health", "/v1/host"}:
                self._send_json(404, {"detail": "Not found"})
                return
            if not self._authorized():
                self._send_json(401, {"detail": "Bearer token required or invalid"})
                return
            if self.path == "/health":
                self._send_json(200, {"status": "healthy", "agent_version": APP_VERSION})
            else:
                self._send_json(200, build_host_info())

        def do_POST(self):
            self._send_json(405, {"detail": "This agent release is read-only"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="JMY-RAS Kali/Linux host agent (read-only)")
    parser.add_argument("--bind", default="127.0.0.1",
                        help="IP address to bind; use the host's Tailscale/WireGuard IP, not 0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    token = load_or_create_token()
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(token))
    server.daemon_threads = True
    print(f"JMY-RAS Linux Host Agent {APP_VERSION} running on http://{args.bind}:{args.port}")
    print(f"Token file: {token_path()} (permissions must remain 600)")
    print("Read-only host inventory only. Stop with Ctrl+C. Do not expose outside a private VPN.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping JMY-RAS agent...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
