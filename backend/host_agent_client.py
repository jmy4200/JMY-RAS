"""Authenticated, allow-listed client for the separate read-only Linux host agent."""
from __future__ import annotations

import ipaddress
import json
import os
import stat
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

TAILSCALE_IPV4_NETWORK = ipaddress.ip_network("100.64.0.0/10")


class HostAgentUnavailable(RuntimeError):
    """Raised when the host agent is not configured or cannot be reached."""


def _configuration() -> tuple[str, str]:
    base_url = os.environ.get("JMY_HOST_AGENT_URL", "").strip().rstrip("/")
    token_file = os.environ.get(
        "JMY_HOST_AGENT_TOKEN_FILE",
        str(Path.home() / ".config" / "jmy-ras" / "agent.token"),
    )
    if not base_url:
        raise HostAgentUnavailable("Host agent URL is not configured")
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise HostAgentUnavailable("Host agent URL must be an HTTP URL on a private interface")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise HostAgentUnavailable("Host agent URL must contain only scheme, address and port")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise HostAgentUnavailable("Host agent URL must use a literal loopback or Tailscale IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise HostAgentUnavailable("Only IPv4 host-agent addresses are supported")
    if not address.is_loopback and address not in TAILSCALE_IPV4_NETWORK:
        raise HostAgentUnavailable("Host agent URL must use loopback or a Tailscale IPv4 address")
    return base_url, token_file


def fetch_host_agent(endpoint: str) -> dict:
    """Fetch a fixed read-only endpoint using the host-agent token kept on the server."""
    if endpoint not in {"/health", "/v1/host"}:
        raise ValueError("Unsupported host-agent endpoint")
    base_url, token_file = _configuration()
    path = Path(token_file).expanduser()
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise HostAgentUnavailable("Host agent token file must be a regular file with mode 600")
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HostAgentUnavailable("Host agent token file is unavailable") from exc
    if len(token) < 40:
        raise HostAgentUnavailable("Host agent token file is invalid")

    request = Request(
        base_url + endpoint,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            raise HostAgentUnavailable("Host agent rejected its configured token") from exc
        raise HostAgentUnavailable(f"Host agent returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise HostAgentUnavailable("Host agent is unreachable or returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise HostAgentUnavailable("Host agent returned an unexpected response")
    return data
