from pathlib import Path


def test_stech_mcp_entrypoint_uses_authoritative_vtex_image_runtime():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'stech-mcp = "stech_mcp.server_authoritative:main"' in text
