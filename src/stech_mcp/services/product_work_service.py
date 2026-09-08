from __future__ import annotations

from typing import Any

from stech_mcp.domain.product_work_models import WORK_TYPES, make_context_hash, normalize_partnumber


_TECHNICAL_INPUT_KEYS = {
    "row_number",
    "partnumber",
    "category_code",
    "channel_code",
    "template_code",
    "requested_fields",
    "source_context",
}


class ProductWorkService:
    def __init__(self, repository: Any):
        self.repository = repository

    def create_job(
        self,
        *,
        rows: list[dict[str, Any]],
        work_type: str,
        source_name: str,
        actor_source: str,
        priority: int = 50,
    ) -> dict[str, Any]:
        normalized_work_type = str(work_type or "").strip().upper()
        if normalized_work_type not in WORK_TYPES:
            raise ValueError(f"invalid work_type: {work_type}")
        if not 0 <= int(priority) <= 100:
            raise ValueError("priority must be between 0 and 100")

        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_row in rows:
            row = dict(raw_row or {})
            pn = normalize_partnumber(row.get("partnumber", ""))
            if not pn:
                continue
            category = str(row.get("category_code") or "").strip().upper() or None
            channel = str(row.get("channel_code") or "").strip().upper() or None
            context_hash = make_context_hash(normalized_work_type, pn, category, channel)

            # Technical enrichment is a product-level action. If the same PN is
            # repeated in one request, keep the first row/context instead of
            # launching duplicate research merely because a later row omits a
            # category/channel value. Other work types retain context-level
            # deduplication.
            dedupe_key = pn if normalized_work_type == "ENRICH_TECHNICAL" else context_hash
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            if normalized_work_type == "ENRICH_TECHNICAL":
                item = {key: row[key] for key in _TECHNICAL_INPUT_KEYS if key in row}
            else:
                item = dict(row)
            item["partnumber"] = pn
            if category:
                item["category_code"] = category
            elif "category_code" in item:
                item.pop("category_code", None)
            if channel:
                item["channel_code"] = channel
            elif "channel_code" in item:
                item.pop("channel_code", None)
            item["context_hash"] = context_hash
            items.append(item)

        if not items:
            raise ValueError("at least one valid partnumber is required")

        return self.repository.create_job(
            work_type=normalized_work_type,
            source_name=str(source_name or "").strip() or "MCP",
            actor_source=str(actor_source or "").strip() or "MCP",
            priority=int(priority),
            items=items,
        )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        return self.repository.get_job(int(job_id))

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_jobs(limit=max(1, min(int(limit), 200)))

    def retry_item(self, item_id: int) -> dict[str, Any]:
        return self.repository.retry_item(int(item_id))

    def cancel_item(self, item_id: int) -> dict[str, Any]:
        return self.repository.cancel_item(int(item_id))
