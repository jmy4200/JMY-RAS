from pathlib import Path
import os
import socket
import stat
from types import SimpleNamespace

import pytest

from host_agent.agent import build_host_info, load_or_create_token, validate_bind_address


def test_agent_token_is_created_with_private_permissions(tmp_path):
    path = tmp_path / "config" / "agent.token"
    token = load_or_create_token(path)
    assert len(token) >= 40
    assert path.read_text().strip() == token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_or_create_token(path) == token


def test_agent_refuses_weak_file_permissions(tmp_path):
    path = tmp_path / "agent.token"
    path.write_text("x" * 60)
    os.chmod(path, 0o644)
    with pytest.raises(RuntimeError, match="Unsafe token permissions"):
        load_or_create_token(path)


def test_host_info_declares_read_only_capabilities():
    info = build_host_info()
    assert info["agent"] == "JMY-RAS Linux Host Agent"
    assert info["capabilities"]["host_inventory"] is True
    assert info["capabilities"]["screen_view"] is False
    assert info["security"]["remote_command_execution"] is False


def test_loopback_bind_is_allowed():
    validate_bind_address("127.0.0.1")


@pytest.mark.parametrize("address", ["0.0.0.0", "192.168.1.20", "::1"])
def test_non_tailscale_bind_addresses_are_rejected(address):
    with pytest.raises(ValueError):
        validate_bind_address(address)


def test_assigned_tailscale_address_is_allowed(monkeypatch):
    monkeypatch.setattr(
        "host_agent.agent.psutil.net_if_addrs",
        lambda: {"tailscale0": [SimpleNamespace(family=socket.AF_INET, address="100.86.190.101")]},
    )
    validate_bind_address("100.86.190.101")


def test_unassigned_tailscale_address_is_rejected(monkeypatch):
    monkeypatch.setattr("host_agent.agent.psutil.net_if_addrs", lambda: {"tailscale0": []})
    with pytest.raises(ValueError, match="not assigned"):
        validate_bind_address("100.86.190.101")
