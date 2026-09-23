from __future__ import annotations

from typing import Any


_REQUIRED_COMMERCIAL_FIELDS = {
    "COOLBOX": (
        "Precio Lista (Full )",
        "Precio Base (Especial)",
        "Stock",
    ),
}


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class ProductApprovalService:
    def __init__(self, product_master_repository: Any):
        self.repository = product_master_repository

    def approve(
        self,
        partnumber: str,
        *,
        marketplace: str = "COOLBOX",
        approved_by: str = "CHATGPT",
        note: str | None = None,
    ) -> dict[str, Any]:
        normalized = str(partnumber or "").strip().upper()
        market = str(marketplace or "COOLBOX").strip().upper()
        actor = str(approved_by or "CHATGPT").strip() or "CHATGPT"

        master = self.repository.get(normalized)
        draft = self.repository.get_latest_draft(normalized, market)
        if master is None or draft is None:
            return {
                "found": False,
                "approved": False,
                "partnumber": normalized,
                "marketplace": market,
                "blocking_reasons": ["draft_not_found"],
            }

        blocking_reasons: list[str] = []
        if int(draft.get("required_missing_count") or 0) > 0:
            blocking_reasons.append("research_required_fields")

        images = self.repository.list_images(normalized)
        if not any(bool(image.get("is_approved")) for image in images):
            blocking_reasons.append("approved_images")

        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        fields = list(payload.get("fields") or [])
        by_name = {
            str(field.get("field") or field.get("field_name") or "").strip(): field
            for field in fields
        }
        for field_name in _REQUIRED_COMMERCIAL_FIELDS.get(market, ()):
            field = by_name.get(field_name)
            if field is None or _is_empty(field.get("value")):
                blocking_reasons.append(f"commercial:{field_name}")

        if blocking_reasons:
            return {
                "found": True,
                "approved": False,
                "partnumber": normalized,
                "marketplace": market,
                "draft_version": draft.get("draft_version"),
                "approval_status": draft.get("approval_status") or "PENDIENTE",
                "blocking_reasons": blocking_reasons,
            }

        approval = self.repository.approve_latest_draft(
            partnumber=normalized,
            marketplace=market,
            approved_by=actor,
            note=note,
        )
        self.repository.add_audit_event(
            partnumber=normalized,
            event_type="CHANNEL_DRAFT_APPROVED",
            actor_source=actor,
            channel=market,
            detail={
                "channel_draft_id": approval.get("channel_draft_id"),
                "draft_version": approval.get("draft_version"),
                "note": note,
            },
        )
        return {
            **approval,
            "approved": True,
            "blocking_reasons": [],
        }
