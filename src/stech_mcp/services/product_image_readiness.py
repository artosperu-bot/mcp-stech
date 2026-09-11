from __future__ import annotations

from typing import Any

_DEFAULT_POLICY = {
    "channel_code": "MASTER",
    "category_code": "DEFAULT",
    "version_code": "V1",
    "required_min": 1,
    "recommended_min": 4,
    "require_main": True,
    "min_width_px": None,
    "min_height_px": None,
    "exactness_policy": "EXACT_PN_REQUIRED",
}


class ProductImageReadinessService:
    """Calculate reusable image readiness without publishing to any channel."""

    def __init__(
        self,
        *,
        product_repository: Any,
        source_image_repository: Any,
        workspace_image_repository: Any,
        policy_repository: Any | None = None,
    ) -> None:
        self.product_repository = product_repository
        self.source_image_repository = source_image_repository
        self.workspace_image_repository = workspace_image_repository
        self.policy_repository = policy_repository or workspace_image_repository

    @staticmethod
    def _normalize_source(partnumber: str, row: dict[str, Any]) -> dict[str, Any]:
        snapshot = str(row.get("part_number_snapshot") or "").strip().upper()
        match = "EXACT" if snapshot and snapshot == partnumber else ("MISMATCH" if snapshot else "UNKNOWN")
        source_url = str(row.get("url_origen") or "").strip()
        deleted = row.get("fecha_eliminacion") is not None or bool(row.get("ruta_papelera"))
        return {
            **row,
            "is_approved": False,
            "source_eligible": bool(match == "EXACT" and source_url and not deleted),
            "partnumber_match": match,
            "position": int(row.get("orden_imagen") or 0),
            "width_px": row.get("ancho_px"),
            "height_px": row.get("alto_px"),
            "source_type": "DELTRON_DB",
        }

    def _policy(self, channel_code: str | None, category_code: str | None) -> dict[str, Any]:
        getter = getattr(self.policy_repository, "get_image_requirement_policy", None)
        if not callable(getter):
            return dict(_DEFAULT_POLICY)
        row = getter(
            str(channel_code or "MASTER").strip().upper(),
            str(category_code or "DEFAULT").strip().upper(),
        )
        return {**_DEFAULT_POLICY, **(row or {})}

    def get(
        self,
        partnumber: str,
        category_code: str | None = None,
        channel_code: str | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            raise LookupError(f"product not found: {pn}")

        source_id = product.get("producto_distribuidor_id")
        source_images: list[dict[str, Any]] = []
        if source_id is not None:
            source_images = [
                self._normalize_source(pn, row)
                for row in self.source_image_repository.list_for_product(int(source_id))
            ]
        workspace_images = list(self.workspace_image_repository.list_images(pn))
        images = [*source_images, *workspace_images]
        policy = self._policy(channel_code, category_code)
        exactness = str(policy.get("exactness_policy") or "EXACT_PN_REQUIRED").upper()

        def usable(image: dict[str, Any]) -> bool:
            return bool(image.get("is_approved")) or bool(image.get("source_eligible"))

        usable_images = [image for image in images if usable(image)]
        approved = [image for image in workspace_images if bool(image.get("is_approved"))]
        exact = [
            image
            for image in usable_images
            if str(image.get("partnumber_match") or "").upper() == "EXACT"
        ]
        has_main = any(int(image.get("position") or 0) == 1 for image in usable_images)
        min_width = policy.get("min_width_px")
        min_height = policy.get("min_height_px")

        def quality_ok(image: dict[str, Any]) -> bool:
            if min_width is None and min_height is None:
                return True
            width = image.get("width_px")
            height = image.get("height_px")
            if width is None or height is None:
                return False
            return (min_width is None or int(width) >= int(min_width)) and (
                min_height is None or int(height) >= int(min_height)
            )

        quality = [image for image in usable_images if quality_ok(image)]
        required = max(int(policy.get("required_min") or 0), 0)
        recommended = max(int(policy.get("recommended_min") or required), required)
        reasons: list[str] = []
        non_exact_approved = any(
            str(image.get("partnumber_match") or "").upper() != "EXACT"
            for image in approved
        )

        if not usable_images:
            reasons.append("no_usable_images")
        if exactness == "EXACT_PN_REQUIRED" and non_exact_approved:
            reasons.append("approved_non_exact_image")
        if bool(policy.get("require_main")) and not has_main:
            reasons.append("main_image_missing")
        if len(usable_images) < required:
            reasons.append("required_count_not_met")
        elif len(usable_images) < recommended:
            reasons.append("recommended_count_not_met")
        if len(quality) < required:
            reasons.append("quality_minimum_not_met")

        if not usable_images:
            state = "NO_IMAGES"
        elif "approved_non_exact_image" in reasons or "main_image_missing" in reasons:
            state = "REVIEW_REQUIRED"
        elif any(
            reason in reasons
            for reason in (
                "required_count_not_met",
                "recommended_count_not_met",
                "quality_minimum_not_met",
            )
        ):
            state = "INCOMPLETE"
        else:
            state = "READY"

        return {
            "found": True,
            "partnumber": pn,
            "state": state,
            "image_count": len(usable_images),
            "source_image_count": len(source_images),
            "workspace_image_count": len(workspace_images),
            "approved_count": len(approved),
            "exact_count": len(exact),
            "has_main": has_main,
            "quality_ok_count": len(quality),
            "required_min": required,
            "recommended_min": recommended,
            "policy": policy,
            "missing_reasons": reasons,
        }