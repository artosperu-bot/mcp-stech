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
    ) -> None:
        self.requirement_repository = requirement_repository
        self.technical_status_service = technical_status_service
        self.image_readiness_service = image_readiness_service

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
        fields: list[dict[str, Any]] = []
        required_missing = 0
        required_conflicts = 0
        channel_input_required = 0

        for raw in requirements.get("fields") or []:
            field = dict(raw)
            target = str(field.get("target_field_code") or "").strip()
            master = str(field.get("master_field_code") or target).strip()
            requirement = str(field.get("requirement") or "OPTIONAL").strip().upper()
            scope = str(field.get("data_scope") or "TECHNICAL").strip().upper()

            if scope in {"COMMERCIAL", "CONTROL"} or not master:
                state = "CHANNEL_INPUT"
                value = None
                if requirement == "REQUIRED":
                    channel_input_required += 1
            elif master.lower() in conflicts:
                state = "CONFLICT"
                value = known.get(master)
                if requirement == "REQUIRED":
                    required_conflicts += 1
            elif master in known and known.get(master) not in (None, ""):
                state = "COMPLETE"
                value = known.get(master)
            else:
                state = "MISSING"
                value = None
                if requirement == "REQUIRED":
                    required_missing += 1

            fields.append(
                {
                    **field,
                    "target_field_code": target,
                    "master_field_code": master or None,
                    "state": state,
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
            state = "BLOCKED_CONFLICT"
        elif required_missing or channel_input_required or image_blocked:
            state = "INCOMPLETE"
        else:
            state = "READY"

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
        return {
            "partnumber": pn,
            "channel_code": channel,
            "platform_code": requirements.get("platform_code"),
            "category_code": category,
            "template_code": requirements.get("template_code"),
            "requirements_version": requirements.get("version_code"),
            "state": state,
            "required_total": required_total,
            "required_complete": required_complete,
            "required_missing": required_missing,
            "required_conflicts": required_conflicts,
            "channel_input_required": channel_input_required,
            "fields": fields,
            "image_readiness": image_readiness,
        }
