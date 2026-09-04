from __future__ import annotations

from decimal import Decimal
from typing import Any

from stech_mcp.domain.packaging_resolver import resolve_package
from stech_mcp.domain.product_readiness import calculate_readiness
from stech_mcp.services.coolbox_preview import _load_specs, _screen, build_coolbox_preview
from stech_mcp.services.product_images import normalize_deltron_images


class ProductPrepareService:
    def __init__(
        self,
        *,
        product_repository: Any,
        enrichment_repository: Any,
        packaging_rule_repository: Any,
        product_master_repository: Any,
        source_image_repository: Any | None = None,
    ) -> None:
        self.product_repository = product_repository
        self.enrichment_repository = enrichment_repository
        self.packaging_rule_repository = packaging_rule_repository
        self.product_master_repository = product_master_repository
        self.source_image_repository = source_image_repository

    def prepare(self, partnumber: str, category: str = "LAPTOP") -> dict[str, Any]:
        normalized = str(partnumber or "").strip().upper()
        product = self.product_repository.get_by_partnumber(normalized)
        if product is None:
            return {"found": False, "partnumber": normalized}

        specs = _load_specs(product)
        screen_value = _screen(specs, str(product.get("nombre") or ""))
        screen_inches = Decimal(str(screen_value)) if screen_value is not None else None

        package = None
        if screen_inches is not None:
            try:
                package = resolve_package(
                    partnumber=normalized,
                    category_code=str(category or "LAPTOP").strip().upper(),
                    screen_inches=screen_inches,
                    enrichment_repository=self.enrichment_repository,
                    packaging_rule_repository=self.packaging_rule_repository,
                )
            except LookupError:
                package = None

        approved_enrichments = self.enrichment_repository.get_approved(normalized)
        preview = build_coolbox_preview(
            product,
            package=package,
            enrichments=approved_enrichments,
        )

        workspace_images = self.product_master_repository.list_images(normalized)
        source_images: list[dict[str, Any]] = []
        source_product_id = product.get("producto_distribuidor_id")
        if self.source_image_repository is not None and source_product_id is not None:
            source_rows = self.source_image_repository.list_for_product(int(source_product_id))
            source_images = normalize_deltron_images(normalized, source_rows)

        images = [*source_images, *workspace_images]
        readiness = calculate_readiness(
            product=product,
            coolbox_preview=preview,
            package=package,
            images=images,
        )

        snapshot = {
            "partnumber": normalized,
            "source_product_id": source_product_id,
            "distributor": product.get("distribuidor"),
            "brand": product.get("marca"),
            "model": specs.get("MODELO"),
            "product_name": product.get("nombre"),
            "ean": product.get("ean"),
            "upc": product.get("upc"),
            "mini_codigo": product.get("mini_codigo") or product.get("minicodigo"),
            "category_code": str(category or "LAPTOP").strip().upper(),
            "subcategory_code": product.get("subcategoria") or product.get("subcategory"),
            "source_stock_value": product.get("stock_valor"),
            "source_stock_operator": product.get("stock_operador"),
            "source_price_usd_sin_igv": product.get("precio_usd_sin_igv"),
            "source_observed_at": product.get("observado_at"),
            "screen_inches": screen_inches,
            "package_width_cm": (package or {}).get("width_cm"),
            "package_length_cm": (package or {}).get("length_cm"),
            "package_height_cm": (package or {}).get("height_cm"),
            "package_weight_g": (package or {}).get("weight_g"),
            "package_status": (package or {}).get("status"),
            "package_method": (package or {}).get("method"),
            "package_source": (package or {}).get("source"),
            "package_rule_code": (package or {}).get("rule_code"),
            "package_confidence_grade": (package or {}).get("confidence_grade"),
            "readiness_state": readiness["state"],
            "identity_score": readiness["identity_score"],
            "technical_score": readiness["technical_score"],
            "image_score": readiness["image_score"],
            "package_score": readiness["package_score"],
            "coolbox_score": readiness["coolbox_score"],
        }
        persisted_master = self.product_master_repository.upsert_master(snapshot)
        draft = self.product_master_repository.replace_draft(
            partnumber=normalized,
            marketplace="COOLBOX",
            template_name=str(preview.get("template") or "Laptops-All in one"),
            payload=preview,
        )
        self.product_master_repository.add_audit_event(
            partnumber=normalized,
            event_type="PRODUCT_PREPARED",
            actor_source="STECH_MCP",
            channel="COOLBOX",
            detail={
                "draft_version": draft.get("draft_version"),
                "field_count": draft.get("field_count"),
                "readiness_state": readiness.get("state"),
                "approved_enrichment_count": len(approved_enrichments),
                "source_image_count": len(source_images),
                "workspace_image_count": len(workspace_images),
                "usable_image_count": readiness.get("usable_image_count"),
            },
        )

        return {
            "found": True,
            "partnumber": normalized,
            "product_master": persisted_master,
            "package": package,
            "readiness": readiness,
            "images": images,
            "source_images": source_images,
            "workspace_images": workspace_images,
            "approved_enrichments": approved_enrichments,
            "coolbox_draft": draft,
            "coolbox_preview": preview,
        }
