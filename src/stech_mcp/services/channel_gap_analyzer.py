from __future__ import annotations

from typing import Any


class ChannelGapAnalyzer:
    """Compare canonical product knowledge with one versioned channel requirement set."""

    def __init__(
        self,
        *,
        requirement_repository: Any,
        technical_status_service: Any,
        image_readiness_service: Any,
        product_repository: Any | None = None,
    ) -> None:
        self.requirement_repository = requirement_repository
        self.technical_status_service = technical_status_service
        self.image_readiness_service = image_readiness_service
        self.product_repository = product_repository

    @staticmethod
    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def get(
        self,
        partnumber: str,
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        channel = str(channel_code or "").strip().upper()
        category = str(category_code or "").strip().upper()
        if not pn or not channel or not category:
            raise ValueError("partnumber, channel_code and category_code are required")

        requirements = self.requirement_repository.get(
            channel,
            category,
            requirements_version,
        )
        if not requirements:
            return {
                "partnumber": pn,
                "channel_code": channel,
                "category_code": category,
                "requirements_version": requirements_version,
                "state": "NOT_CONFIGURED",
                "channel_export_status": "NOT_CONFIGURED",
                "completion_pct": 0,
                "missing_count": 0,
                "conflict_count": 0,
                "fields": [],
                "image_readiness": None,
            }

        technical = self.technical_status_service.get(pn)
        known = dict(technical.get("known_fields") or {})
        conflicts = {
            str(value or "").strip().lower()
            for value in (technical.get("conflicts") or [])
            if str(value or "").strip()
        }
        product = (
            self.product_repository.get_by_partnumber(pn)
            if self.product_repository is not None
            else {}
        ) or {}

        fields: list[dict[str, Any]] = []
        required_missing = 0
        required_conflicts = 0
        channel_input_required = 0
        logistics_required = 0
        identity_required_missing = 0

        for raw in requirements.get("fields") or []:
            field = dict(raw)
            target = str(field.get("target_field_code") or "").strip()
            master = str(field.get("master_field_code") or target).strip()
            requirement = str(field.get("requirement") or "OPTIONAL").strip().upper()
            scope = str(field.get("data_scope") or "TECHNICAL").strip().upper()

            if scope == "IDENTITY":
                aliases = {
                    "ean": ("ean",),
                    "upc": ("upc",),
                    "barcode": ("ean", "upc"),
                    "partnumber": ("partnumber", "part_number"),
                    "brand": ("brand", "marca"),
                    "model": ("model", "modelo"),
                }.get(master.lower(), (master,))
                value = next((product.get(key) for key in aliases if self._present(product.get(key))), None)
                if self._present(value):
                    field_state = "COMPLETE"
                else:
                    field_state = "MISSING"
                    if requirement == "REQUIRED":
                        required_missing += 1
                        identity_required_missing += 1
            elif scope in {"COMMERCIAL", "CONTROL"} or not master:
                field_state = "CHANNEL_INPUT"
                value = None
                if requirement == "REQUIRED":
                    channel_input_required += 1
                    if scope == "CONTROL":
                        logistics_required += 1
            elif master.lower() in conflicts:
                field_state = "CONFLICT"
                value = known.get(master)
                if requirement == "REQUIRED":
                    required_conflicts += 1
            elif master in known and self._present(known.get(master)):
                field_state = "COMPLETE"
                value = known.get(master)
            else:
                field_state = "MISSING"
                value = None
                if requirement == "REQUIRED":
                    required_missing += 1

            fields.append(
                {
                    **field,
                    "target_field_code": target,
                    "master_field_code": master or None,
                    "state": field_state,
                    "status": field_state,
                    "value": value,
                }
            )

        image_readiness = self.image_readiness_service.get(
            pn,
            category_code=category,
            channel_code=channel,
        )
        image_blocked = str(image_readiness.get("state") or "").upper() != "READY"

        if required_conflicts:
            overall_state = "BLOCKED_CONFLICT"
            channel_export_status = "REVIEW_REQUIRED"
        elif identity_required_missing:
            overall_state = "INCOMPLETE"
            channel_export_status = "BLOCKED_IDENTITY"
        elif required_missing:
            overall_state = "INCOMPLETE"
            channel_export_status = "BLOCKED_REQUIRED_FIELD"
        elif logistics_required:
            overall_state = "INCOMPLETE"
            channel_export_status = "BLOCKED_LOGISTICS"
        elif channel_input_required:
            overall_state = "INCOMPLETE"
            channel_export_status = "BLOCKED_REQUIRED_FIELD"
        elif image_blocked:
            overall_state = "INCOMPLETE"
            channel_export_status = "BLOCKED_IMAGES"
        else:
            overall_state = "READY"
            channel_export_status = "READY"

        required_total = sum(
            1
            for field in fields
            if str(field.get("requirement") or "").upper() == "REQUIRED"
        )
        required_complete = sum(
            1
            for field in fields
            if str(field.get("requirement") or "").upper() == "REQUIRED"
            and field.get("state") == "COMPLETE"
        )
        completion_pct = round((required_complete / required_total) * 100) if required_total else 100
        return {
            "partnumber": pn,
            "channel_code": channel,
            "platform_code": requirements.get("platform_code"),
            "category_code": category,
            "template_code": requirements.get("template_code"),
            "requirements_version": requirements.get("version_code"),
            "state": overall_state,
            "channel_export_status": channel_export_status,
            "completion_pct": completion_pct,
            "missing_count": required_missing,
            "conflict_count": required_conflicts,
            "required_total": required_total,
            "required_complete": required_complete,
            "required_missing": required_missing,
            "required_conflicts": required_conflicts,
            "channel_input_required": channel_input_required,
            "logistics_required": logistics_required,
            "identity_required_missing": identity_required_missing,
            "fields": fields,
            "image_readiness": image_readiness,
        }
