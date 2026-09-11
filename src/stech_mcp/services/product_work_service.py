from __future__ import annotations

from typing import Any

from stech_mcp.domain.product_work_models import WORK_TYPES, make_context_hash, normalize_partnumber


_TECHNICAL_INPUT_KEYS = {
    "row_number",
    "partnumber",
    "category_code",
    "channel_code",
    "template_code",
    "requirements_version",
    "requested_fields",
    "scope",
    "source_context",
}
_IDENTITY_INPUT_KEYS = {
    "partnumber",
    "requested_fields",
    "scope",
    "source_context",
}
_CONTEXT_KEYS = (
    "scope",
    "requirements_version",
    "template_code",
    "requested_fields",
    "image_target_count",
)


class ProductWorkService:
    def __init__(self, repository: Any, *, max_attempts: int = 3):
        normalized_max_attempts = int(max_attempts)
        if not 1 <= normalized_max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        self.repository = repository
        self.max_attempts = normalized_max_attempts

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
            extra_context = {
                key: row.get(key)
                for key in _CONTEXT_KEYS
                if row.get(key) not in (None, "", [])
            }
            context_hash = make_context_hash(
                normalized_work_type,
                pn,
                category,
                channel,
                context=extra_context or None,
            )

            # Preserve legacy product-level technical deduplication when callers
            # do not provide an explicit scope/target. New MASTER/CHANNEL jobs use
            # their intent hash so two different gaps for one PN can coexist.
            contextual = bool(extra_context or channel)
            dedupe_key = (
                pn
                if normalized_work_type == "ENRICH_TECHNICAL" and not contextual
                else context_hash
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            if normalized_work_type == "ENRICH_TECHNICAL":
                item = {key: row[key] for key in _TECHNICAL_INPUT_KEYS if key in row}
            elif normalized_work_type == "RESEARCH_IDENTITY":
                # Identity work is deliberately isolated from commercial data.
                # Persist only the exact PN plus identity research context so a
                # caller cannot smuggle price/stock/publication mutations into
                # this queue item even though those values would be ignored by
                # the handler.
                item = {key: row[key] for key in _IDENTITY_INPUT_KEYS if key in row}
            else:
                item = dict(row)
            item["partnumber"] = pn
            if normalized_work_type == "RESEARCH_IDENTITY":
                item.pop("category_code", None)
                item.pop("channel_code", None)
            else:
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
            max_attempts=self.max_attempts,
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
