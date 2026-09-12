from pathlib import Path


def test_stech_mcp_entrypoint_uses_runtime_wrapper():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'stech-mcp = "stech_mcp.runtime_main:main"' in text


def test_runtime_wrapper_starts_authoritative_runtime_and_enabled_chatgpt_bridge():
    text = Path("src/stech_mcp/runtime_main.py").read_text(encoding="utf-8")
    assert "server_authoritative" in text
    assert "build_runner_from_environment" in text
    assert "start_bridge_thread" in text
