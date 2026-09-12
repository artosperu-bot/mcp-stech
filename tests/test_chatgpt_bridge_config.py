from __future__ import annotations

from importlib import import_module, util
from pathlib import Path

import pytest

from stech_mcp.config import Settings


def bridge_config_module():
    spec = util.find_spec("stech_mcp.chatgpt_bridge.config")
    assert spec is not None, "ChatGPT bridge config module must exist"
    module = import_module("stech_mcp.chatgpt_bridge.config")
    assert hasattr(module, "BridgeConfig")
    return module


def test_bridge_config_loads_from_typed_settings_without_api_keys(tmp_path):
    module = bridge_config_module()
    settings = Settings(
        _env_file=None,
        stech_chatgpt_bridge_enabled=True,
        stech_research_git_repo=str(tmp_path),
        stech_research_git_branch="feat/chatgpt-research-bridge-v1",
        stech_research_max_export_per_cycle=10,
        stech_research_max_import_per_cycle=20,
        stech_research_poll_seconds=60,
    )

    config = module.BridgeConfig.from_settings(settings)

    assert config.enabled is True
    assert config.repo_path == Path(tmp_path)
    assert config.branch == "feat/chatgpt-research-bridge-v1"
    assert config.max_export_per_cycle == 10
    assert config.max_import_per_cycle == 20
    assert config.poll_seconds == 60
    assert not hasattr(config, "openai_api_key")
    assert not hasattr(config, "brave_api_key")


@pytest.mark.parametrize(
    "field,value",
    [
        ("stech_research_max_export_per_cycle", 0),
        ("stech_research_max_import_per_cycle", 0),
        ("stech_research_poll_seconds", 0),
    ],
)
def test_bridge_settings_reject_non_positive_limits(field, value):
    values = {field: value}
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)
