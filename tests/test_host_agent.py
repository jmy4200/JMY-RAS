from pathlib import Path
import os
import stat

import pytest

from host_agent.agent import build_host_info, load_or_create_token


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
