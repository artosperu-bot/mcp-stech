from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1
from stech_mcp.chatgpt_bridge.mailbox import Mailbox


def make_request_id(item_id: int, context_hash: str) -> str:
    safe_hash = "".join(ch for ch in str(context_hash or "").lower() if ch.isalnum())
    suffix = (safe_hash[:12] or "nohash000000")
    return f"rw_{int(item_id)}_{suffix}"


class ResearchRequestExporter:
    def __init__(self, work_repository: Any, product_repository: Any, mailbox: Mailbox) -> None:
        self.work_repository = work_repository
        self.product_repository = product_repository
        self.mailbox = mailbox

    @staticmethod
    def _requested_fields(item: dict[str, Any]) -> list[str]:
        payload = item.get("input") if isinstance(item.get("input"), dict) else {}
        work_type = str(item.get("work_type") or "").strip().upper()
        fields = payload.get("requested_fields")
        if isinstance(fields, list) and fields:
            return [str(value).strip() for value in fields if str(value).strip()]
        if work_type == "RESEARCH_IMAGES":
            return ["images"]
        if work_type == "RESEARCH_IDENTITY":
            return ["ean", "upc", "gtin"]
        return []

    def _build_request(self, item: dict[str, Any]) -> ResearchRequestV1:
        pn = str(item.get("partnumber") or "").strip().upper()
        product = self.product_repository.get_by_partnumber(pn) or {}
        created_at = item.get("created_at")
        if not isinstance(created_at, datetime):
            created_at = datetime.now(timezone.utc)
        return ResearchRequestV1(
            request_id=make_request_id(int(item["item_id"]), str(item.get("context_hash") or "")),
            created_at=created_at,
            product_work_item_id=int(item["item_id"]),
            product_work_job_id=int(item["job_id"]),
            work_type=str(item.get("work_type") or "").strip().upper(),
            partnumber=pn,
            brand=str(product.get("marca") or product.get("brand") or "").strip() or None,
            model=str(product.get("modelo") or product.get("model") or "").strip() or None,
            category_code=str(item.get("category_code") or "").strip() or None,
            requested_fields=self._requested_fields(item),
            research_policy={
                "exact_partnumber_required": True,
                "prefer_official_sources": True,
                "max_sources": 5,
                "max_candidates": 10,
            },
        )

    def export_waiting(self, *, limit: int = 10) -> list[ResearchRequestV1]:
        rows = self.work_repository.list_waiting_external(limit=limit)
        output: list[ResearchRequestV1] = []
        for item in rows:
            request = self._build_request(item)
            self.mailbox.write_request(request)
            output.append(request)
        return output
