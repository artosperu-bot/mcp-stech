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

    @staticmethod
    def _repo_path(value: str) -> Path:
        configured = Path(str(value or ".").strip() or ".").expanduser()
        if str(value or ".").strip() not in {"", ".", "./", ".\\"}:
            return configured

        current = Path.cwd().resolve()
        if current.name.lower().endswith("-bridge"):
            return current
        sibling = current.parent / f"{current.name}-bridge"
        return sibling.resolve() if sibling.exists() else current

    @classmethod
    def from_settings(cls, settings: Settings) -> "BridgeConfig":
        return cls(
            enabled=settings.stech_chatgpt_bridge_enabled,
            repo_path=cls._repo_path(settings.stech_research_git_repo),
            branch=settings.stech_research_git_branch,
            max_export_per_cycle=settings.stech_research_max_export_per_cycle,
            max_import_per_cycle=settings.stech_research_max_import_per_cycle,
            poll_seconds=settings.stech_research_poll_seconds,
        )
