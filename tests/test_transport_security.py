from stech_mcp.config import Settings
from stech_mcp.server import build_transport_security


def test_public_mcp_hostname_is_allowed():
    settings = Settings(_env_file=None, mcp_public_host="mcp.artos.pe")

    security = build_transport_security(settings)

    assert "mcp.artos.pe" in security.allowed_hosts
    assert "mcp.artos.pe:*" in security.allowed_hosts
    assert "localhost:*" in security.allowed_hosts
    assert "127.0.0.1:*" in security.allowed_hosts
