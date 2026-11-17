import os
import stat
from urllib.error import HTTPError
from io import BytesIO

import pytest

from backend.host_agent_client import (
    HostAgentUnavailable,
    _configuration,
    fetch_host_agent,
)


def configure_agent(monkeypatch, tmp_path):
    token_file = tmp_path / "agent.token"
    token_file.write_text("t" * 60)
    os.chmod(token_file, 0o600)
    monkeypatch.setenv("JMY_HOST_AGENT_URL", "http://100.86.190.101:8765")
    monkeypatch.setenv("JMY_HOST_AGENT_TOKEN_FILE", str(token_file))
    return token_file


def test_host_agent_requires_configuration(monkeypatch):
    monkeypatch.delenv("JMY_HOST_AGENT_URL", raising=False)
    with pytest.raises(HostAgentUnavailable, match="not configured"):
        _configuration()


@pytest.mark.parametrize("url", [
    "http://192.168.1.10:8765",
    "http://0.0.0.0:8765",
    "https://100.86.190.101:8765",
    "http://example.com:8765",
])
def test_host_agent_rejects_non_private_or_invalid_urls(monkeypatch, url):
    monkeypatch.setenv("JMY_HOST_AGENT_URL", url)
    with pytest.raises(HostAgentUnavailable):
        _configuration()


def test_host_agent_client_sends_server_side_bearer_token(monkeypatch, tmp_path):
    configure_agent(monkeypatch, tmp_path)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"status":"healthy","agent_version":"0.1.0"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("backend.host_agent_client.urlopen", fake_urlopen)
    result = fetch_host_agent("/health")
    assert result["status"] == "healthy"
    assert captured["url"] == "http://100.86.190.101:8765/health"
    assert captured["authorization"] == "Bearer " + "t" * 60
    assert captured["timeout"] == 3


def test_host_agent_token_file_permissions_are_enforced(monkeypatch, tmp_path):
    token_file = configure_agent(monkeypatch, tmp_path)
    os.chmod(token_file, 0o644)
    with pytest.raises(HostAgentUnavailable, match="mode 600"):
        fetch_host_agent("/health")


def test_host_agent_rejects_unknown_endpoint(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported"):
        fetch_host_agent("/shutdown")


def test_host_agent_upstream_unauthorized_is_not_exposed(monkeypatch, tmp_path):
    configure_agent(monkeypatch, tmp_path)

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("backend.host_agent_client.urlopen", fake_urlopen)
    with pytest.raises(HostAgentUnavailable, match="rejected"):
        fetch_host_agent("/health")
