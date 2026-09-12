from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from stech_mcp.config import Settings


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    repo_path: Path
    branch: str = Field(min_length=1, max_length=200)
    max_export_per_cycle: int = Field(ge=1, le=100)
    max_import_per_cycle: int = Field(ge=1, le=100)
    poll_seconds: int = Field(ge=1, le=3600)

    @classmethod
    def from_settings(cls, settings: Settings) -> "BridgeConfig":
        return cls(
            enabled=settings.stech_chatgpt_bridge_enabled,
            repo_path=Path(settings.stech_research_git_repo).expanduser(),
            branch=settings.stech_research_git_branch,
            max_export_per_cycle=settings.stech_research_max_export_per_cycle,
            max_import_per_cycle=settings.stech_research_max_import_per_cycle,
            poll_seconds=settings.stech_research_poll_seconds,
        )
