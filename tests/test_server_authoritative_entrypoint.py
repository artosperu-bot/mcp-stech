from pathlib import Path


def test_stech_mcp_entrypoint_uses_authoritative_vtex_image_runtime():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'stech-mcp = "stech_mcp.server_authoritative:main"' in text


def test_authoritative_runtime_starts_enabled_chatgpt_bridge_inside_stech_mcp():
    text = Path("src/stech_mcp/server_authoritative.py").read_text(encoding="utf-8")
    assert "build_runner_from_environment" in text
    assert "start_bridge_thread" in text
    assert "_chatgpt_bridge_thread" in text
