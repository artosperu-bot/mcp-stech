from __future__ import annotations

from typing import Any


class ChannelDraftService:
    """Create a versioned preparation snapshot only when channel readiness is safe."""

    def __init__(self, *, gap_analyzer: Any, draft_repository: Any) -> None:
        self.gap_analyzer = gap_analyzer
        self.draft_repository = draft_repository

    def prepare(
        self,
        partnumber: str,
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        channel = str(channel_code or "").strip().upper()
        category = str(category_code or "").strip().upper()
        gap = self.gap_analyzer.get(
            pn,
            channel,
            category,
            requirements_version,
        )
        if gap.get("state") != "READY":
            return {
                "created": False,
                "state": "BLOCKED",
                "partnumber": pn,
                "channel_code": channel,
                "gap": gap,
            }

        version = str(gap.get("requirements_version") or requirements_version or "CURRENT")
        payload = {
            "partnumber": pn,
            "channel_code": channel,
            "platform_code": gap.get("platform_code"),
            "category_code": category,
            "requirements_version": version,
            "template_code": gap.get("template_code"),
            "fields": list(gap.get("fields") or []),
            "image_readiness": gap.get("image_readiness"),
        }
        draft = self.draft_repository.replace_draft(
            partnumber=pn,
            marketplace=channel,
            template_name=version,
            payload=payload,
        )
        return {
            "created": True,
            "state": "READY",
            "partnumber": pn,
            "channel_code": channel,
            "gap": gap,
            "draft": draft,
        }
