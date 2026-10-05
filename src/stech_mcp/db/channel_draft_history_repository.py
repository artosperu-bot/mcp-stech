from __future__ import annotations

from typing import Any, Callable


class ChannelDraftHistoryRepository:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def list_drafts(
        self,
        partnumber: str,
        marketplace: str | None = None,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        channel = str(marketplace or "").strip().upper() or None
        bounded = max(1, min(int(limit), 100))
        if not pn:
            raise ValueError("partnumber is required")

        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            if channel:
                cur.execute(
                    f"""
SELECT TOP ({bounded})
    channel_draft_id, partnumber, marketplace, template_name, draft_version,
    status, field_count, required_missing_count, estimated_count,
    approval_status, approved_by, approved_at, approval_note,
    created_at, updated_at
FROM dbo.channel_draft
WHERE partnumber = ? AND marketplace = ?
ORDER BY draft_version DESC, channel_draft_id DESC;
""",
                    pn,
                    channel,
                )
            else:
                cur.execute(
                    f"""
SELECT TOP ({bounded})
    channel_draft_id, partnumber, marketplace, template_name, draft_version,
    status, field_count, required_missing_count, estimated_count,
    approval_status, approved_by, approved_at, approval_note,
    created_at, updated_at
FROM dbo.channel_draft
WHERE partnumber = ?
ORDER BY created_at DESC, channel_draft_id DESC;
""",
                    pn,
                )
            columns = [str(item[0]) for item in (cur.description or [])]
            return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]
        finally:
            conn.close()
