from __future__ import annotations

from decimal import Decimal
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from stech_mcp.config import Settings
from stech_mcp.db.connection import make_mcp_connection_factory, make_source_connection_factory, sql_ping
from stech_mcp.db.deltron_image_repository import DeltronImageRepository
from stech_mcp.db.enrichment_repository import EnrichmentRepository
from stech_mcp.db.packaging_rule_repository import PackagingRuleRepository
from stech_mcp.db.product_identity_repository import ProductIdentityRepository
from stech_mcp.db.product_identity_research_repository import ProductIdentityResearchRepository
from stech_mcp.db.product_master_repository import ProductMasterRepository
from stech_mcp.db.product_repository import ProductRepository
from stech_mcp.domain.packaging_resolver import resolve_package
from stech_mcp.domain.packaging_rules import estimate_package_weight, validate_package_dimensions
from stech_mcp.services.coolbox_preview import _load_specs, _screen, build_coolbox_preview
from stech_mcp.services.marketplace_preview import build_marketplace_preview
from stech_mcp.services.product_approval import ProductApprovalService
from stech_mcp.services.product_field_verification import ProductFieldVerificationService
from stech_mcp.services.product_identity_derivation import ProductIdentityDerivationService
from stech_mcp.services.product_identity_promotion import ProductIdentityPromotionService
from stech_mcp.services.product_identity_research import ProductIdentityResearchService
from stech_mcp.services.product_images import normalize_deltron_images
from stech_mcp.services.product_prepare import ProductPrepareService
from stech_mcp.tools.core import health_snapshot

settings = Settings()
source_connection_factory = make_source_connection_factory(settings)
mcp_connection_factory = make_mcp_connection_factory(settings)
product_repository = ProductRepository(source_connection_factory, view_name=settings.erp_product_view)
product_identity_repository = ProductIdentityRepository(source_connection_factory)
product_identity_research_repository = ProductIdentityResearchRepository(mcp_connection_factory)
deltron_image_repository = DeltronImageRepository(source_connection_factory)
enrichment_repository = EnrichmentRepository(mcp_connection_factory)
packaging_rule_repository = PackagingRuleRepository(mcp_connection_factory)
product_master_repository = ProductMasterRepository(mcp_connection_factory)
product_prepare_service = ProductPrepareService(
    product_repository=product_repository,
    enrichment_repository=enrichment_repository,
    packaging_rule_repository=packaging_rule_repository,
    product_master_repository=product_master_repository,
    source_image_repository=deltron_image_repository,
)
product_approval_service = ProductApprovalService(product_master_repository)
product_field_verification_service = ProductFieldVerificationService(enrichment_repository)
product_identity_promotion_service = ProductIdentityPromotionService(
    enrichment_repository=enrichment_repository,
    identity_repository=product_identity_repository,
    audit_repository=product_master_repository,
)
product_identity_derivation_service = ProductIdentityDerivationService(
    identity_repository=product_identity_repository,
    audit_repository=product_master_repository,
)
product_identity_research_service = ProductIdentityResearchService(
    identity_repository=product_identity_repository,
    research_repository=product_identity_research_repository,
    verification_service=product_field_verification_service,
    promotion_service=product_identity_promotion_service,
)

mcp = MCPServer("STECH MCP")


def build_transport_security(current_settings: Settings) -> TransportSecuritySettings:
    public_host = current_settings.mcp_public_host.strip()
    allowed_hosts = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
    ]
    allowed_origins: list[str] = []
    if public_host:
        allowed_hosts.extend([public_host, f"{public_host}:*"])
        allowed_origins.append(f"https://{public_host}")

    return TransportSecuritySettings(
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def _product_screen_inches(product: dict[str, Any]) -> Decimal | None:
    specs = _load_specs(product)
    value = _screen(specs, str(product.get("nombre") or ""))
    return Decimal(str(value)) if value is not None else None


def _resolve_product_package(product: dict[str, Any], category: str) -> dict[str, Any] | None:
    screen_inches = _product_screen_inches(product)
    if screen_inches is None:
        return None
    try:
        return resolve_package(
            partnumber=str(product.get("part_number") or product.get("partnumber") or "").strip(),
            category_code=category.strip().upper(),
            screen_inches=screen_inches,
            enrichment_repository=enrichment_repository,
            packaging_rule_repository=packaging_rule_repository,
        )
    except LookupError:
        return None


@mcp.tool()
def stech_health() -> dict[str, Any]:
    """Comprueba que el MCP está vivo y que SQL Server responde."""
    return health_snapshot(lambda: sql_ping(source_connection_factory))


@mcp.tool()
def product_get(partnumber: str) -> dict[str, Any]:
    """Obtiene un producto real de V8 por Part Number desde V_PRD_PRODUCTO_ACTUAL."""
    product = product_repository.get_by_partnumber(partnumber)
    return {
        "found": product is not None,
        "partnumber": partnumber.strip(),
        "product": product,
    }


@mcp.tool()
def product_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Busca productos V8 por PN, EAN, UPC, mini código, código externo o nombre."""
    rows = product_repository.search(query, limit=limit)
    return {
        "query": query.strip(),
        "count": len(rows),
        "products": rows,
    }


@mcp.tool()
def product_history(partnumber: str, limit: int = 25) -> dict[str, Any]:
    """Obtiene observaciones reales V8 del producto: fecha, stock, precio y ubicaciones."""
    rows = product_repository.history(partnumber, limit=limit)
    return {
        "partnumber": partnumber.strip(),
        "count": len(rows),
        "observations": rows,
        "source_view": "dbo.V_HST_PRODUCTO_OBSERVACION_V8",
        "synthetic_intervals": False,
    }


@mcp.tool()
def coolbox_preview(partnumber: str) -> dict[str, Any]:
    """Prepara las 81 columnas Coolbox usando Deltron + enriquecimientos aprobados + empaque resuelto."""
    normalized = partnumber.strip().upper()
    product = product_repository.get_by_partnumber(normalized)
    if product is None:
        return {
            "found": False,
            "partnumber": normalized,
            "template": "Laptops-All in one",
            "fields": [],
        }
    package = _resolve_product_package(product, "LAPTOP")
    enrichments = enrichment_repository.get_approved(normalized)
    preview = build_coolbox_preview(product, package=package, enrichments=enrichments)
    return {"found": True, **preview}


@mcp.tool()
def packaging_estimate_weight(
    screen_inches: float,
    device_weight_kg: float,
    is_gaming: bool = False,
) -> dict[str, Any]:
    """Estima peso de empaque solo cuando no existe una fuente confiable real."""
    estimated = estimate_package_weight(
        screen_inches=Decimal(str(screen_inches)),
        device_weight_kg=Decimal(str(device_weight_kg)),
        is_gaming=is_gaming,
    )
    return {
        "estimated_package_weight_kg": float(estimated),
        "method": "ESTIMATED",
        "requires_source_search_first": True,
    }


@mcp.tool()
def packaging_validate_dimensions(
    device_width_cm: float,
    device_depth_cm: float,
    device_height_cm: float,
    package_width_cm: float,
    package_length_cm: float,
    package_height_cm: float,
) -> dict[str, Any]:
    """Valida que las dimensiones declaradas de una caja sean físicamente mayores al equipo."""
    valid, reasons = validate_package_dimensions(
        device_width_cm=Decimal(str(device_width_cm)),
        device_depth_cm=Decimal(str(device_depth_cm)),
        device_height_cm=Decimal(str(device_height_cm)),
        package_width_cm=Decimal(str(package_width_cm)),
        package_length_cm=Decimal(str(package_length_cm)),
        package_height_cm=Decimal(str(package_height_cm)),
    )
    return {"valid": valid, "reasons": reasons}


@mcp.tool()
def packaging_rule_get(screen_inches: float, category: str = "LAPTOP") -> dict[str, Any]:
    """Devuelve la regla de empaque S-TECH aplicable sin presentarla como dato oficial."""
    rule = packaging_rule_repository.match(
        category.strip().upper(),
        Decimal(str(screen_inches)),
    )
    return {"found": rule is not None, "rule": rule}


@mcp.tool()
def packaging_resolve(partnumber: str, category: str = "LAPTOP") -> dict[str, Any]:
    """Resuelve empaque: primero enrichment aprobado; si falta, aplica regla S-TECH compatible."""
    normalized = partnumber.strip().upper()
    product = product_repository.get_by_partnumber(normalized)
    if product is None:
        return {"found": False, "partnumber": normalized, "package": None}

    screen_inches = _product_screen_inches(product)
    if screen_inches is None:
        return {
            "found": True,
            "partnumber": normalized,
            "package": None,
            "reason": "screen_inches_not_found",
        }

    try:
        package = resolve_package(
            partnumber=normalized,
            category_code=category.strip().upper(),
            screen_inches=screen_inches,
            enrichment_repository=enrichment_repository,
            packaging_rule_repository=packaging_rule_repository,
        )
    except LookupError:
        package = None

    return {
        "found": True,
        "partnumber": normalized,
        "screen_inches": screen_inches,
        "package": package,
        "reason": None if package is not None else "no_package_rule_or_approved_enrichment",
    }


@mcp.tool()
def marketplace_preview(partnumber: str, marketplace: str, category: str = "LAPTOP") -> dict[str, Any]:
    """Genera preview multicanal; Fase 1 habilita COOLBOX/LAPTOP con ficha maestra reutilizable."""
    normalized = partnumber.strip().upper()
    product = product_repository.get_by_partnumber(normalized)
    if product is None:
        return {
            "found": False,
            "partnumber": normalized,
            "marketplace": marketplace.strip().upper(),
            "category": category.strip().upper(),
            "fields": [],
        }

    package = _resolve_product_package(product, category)
    preview = build_marketplace_preview(
        product=product,
        marketplace=marketplace,
        category=category,
        package=package,
    )
    return {"found": True, **preview}


@mcp.tool()
def product_prepare(partnumber: str, category: str = "LAPTOP") -> dict[str, Any]:
    """Prepara y persiste el Product Workspace sin publicar en ningún marketplace."""
    return product_prepare_service.prepare(partnumber, category=category)


@mcp.tool()
def product_master_get(partnumber: str) -> dict[str, Any]:
    """Lee el Product Master persistido y su inventario de imágenes metadata."""
    normalized = partnumber.strip().upper()
    master = product_master_repository.get(normalized)
    images = product_master_repository.list_images(normalized) if master is not None else []
    return {
        "found": master is not None,
        "partnumber": normalized,
        "master": master,
        "images": images,
    }


@mcp.tool()
def product_readiness_get(partnumber: str) -> dict[str, Any]:
    """Devuelve readiness persistido, draft Coolbox e inventario real de imágenes."""
    normalized = partnumber.strip().upper()
    master = product_master_repository.get(normalized)
    if master is None:
        return {"found": False, "partnumber": normalized, "readiness": None}
    draft = product_master_repository.get_latest_draft(normalized, "COOLBOX")
    image_inventory = product_images_get(normalized)
    return {
        "found": True,
        "partnumber": normalized,
        "readiness": {
            "state": master.get("readiness_state"),
            "identity_score": master.get("identity_score"),
            "technical_score": master.get("technical_score"),
            "image_score": master.get("image_score"),
            "package_score": master.get("package_score"),
            "coolbox_score": master.get("coolbox_score"),
            "image_count": image_inventory.get("image_count", 0),
            "source_image_count": image_inventory.get("source_image_count", 0),
            "workspace_image_count": image_inventory.get("workspace_image_count", 0),
            "usable_image_count": image_inventory.get("usable_image_count", 0),
            "approved_image_count": image_inventory.get("approved_image_count", 0),
            "coolbox_field_count": (draft or {}).get("field_count") or master.get("coolbox_field_count"),
            "coolbox_required_missing_count": (draft or {}).get("required_missing_count") or master.get("coolbox_required_missing_count"),
            "coolbox_estimated_count": (draft or {}).get("estimated_count") or master.get("coolbox_estimated_count"),
            "coolbox_approval_status": (draft or {}).get("approval_status") or master.get("coolbox_approval_status"),
        },
    }


@mcp.tool()
def channel_draft_get(partnumber: str, marketplace: str = "COOLBOX") -> dict[str, Any]:
    """Devuelve el último draft versionado de un canal; V1 usa principalmente COOLBOX."""
    normalized = partnumber.strip().upper()
    market = marketplace.strip().upper()
    draft = product_master_repository.get_latest_draft(normalized, market)
    if draft is None:
        return {"found": False, "partnumber": normalized, "marketplace": market, "draft": None}
    payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
    out = {**draft, "fields": list(payload.get("fields") or [])}
    return {"found": True, "partnumber": normalized, "marketplace": market, "draft": out}


@mcp.tool()
def product_approve(
    partnumber: str,
    marketplace: str = "COOLBOX",
    approved_by: str = "CHATGPT",
    note: str | None = None,
) -> dict[str, Any]:
    """Aprueba la versión exacta del último draft solo si ficha, imágenes y datos comerciales están listos."""
    return product_approval_service.approve(
        partnumber,
        marketplace=marketplace,
        approved_by=approved_by,
        note=note,
    )


@mcp.tool()
def product_field_verify(
    partnumber: str,
    field_code: str,
    confidence_grade: str,
    source_url: str,
    source_type: str,
    source_partnumber: str,
    evidence_text: str,
    value_text: str | None = None,
    value_number: float | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Guarda un dato técnico como VERIFIED; aliases comunes se normalizan y errores de validación no rompen el lote."""
    try:
        return product_field_verification_service.verify(
            partnumber=partnumber,
            field_code=field_code,
            value_text=value_text,
            value_number=value_number,
            unit=unit,
            confidence_grade=confidence_grade,
            source_url=source_url,
            source_type=source_type,
            source_partnumber=source_partnumber,
            evidence_text=evidence_text,
        )
    except ValueError as exc:
        return {
            "verified": False,
            "status": "VALIDATION_ERROR",
            "partnumber": str(partnumber or "").strip().upper(),
            "field_code": str(field_code or "").strip().lower(),
            "error": str(exc),
            "retryable": True,
        }


@mcp.tool()
def product_enrichment_get(partnumber: str) -> dict[str, Any]:
    """Devuelve todos los enriquecimientos aprobados que el Product Workspace reutiliza."""
    normalized = partnumber.strip().upper()
    rows = enrichment_repository.get_approved(normalized)
    return {
        "found": bool(rows),
        "partnumber": normalized,
        "count": len(rows),
        "enrichments": rows,
    }


@mcp.tool()
def product_identity_missing_list(
    after_id: int = 0,
    limit: int = 100,
    distributor: str | None = None,
) -> dict[str, Any]:
    """Lista productos activos con Part Number y EAN/UPC faltante, con paginación estable."""
    result = product_identity_repository.list_missing_identifiers(
        after_id=after_id,
        limit=limit,
        distributor=distributor,
    )
    return {
        "after_id": max(0, int(after_id or 0)),
        "distributor": str(distributor).strip().upper() if distributor else None,
        **result,
    }


@mcp.tool()
def product_identity_promote_verified(
    partnumber: str,
    identifier_type: str,
    approved_by: str = "CHATGPT",
) -> dict[str, Any]:
    """Promueve un EAN/UPC/GTIN VERIFIED al catálogo operativo sin sobrescribir conflictos."""
    return product_identity_promotion_service.promote(
        partnumber,
        identifier_type,
        approved_by=approved_by,
    )


@mcp.tool()
def product_identity_derive_equivalent(
    partnumber: str,
    actor: str = "STECH_MCP",
) -> dict[str, Any]:
    """Deriva UPC-A↔EAN/GTIN-13 equivalente desde un identificador operativo válido, sin Internet."""
    try:
        return product_identity_derivation_service.derive_for_partnumber(partnumber, actor=actor)
    except ValueError as exc:
        return {
            "found": False,
            "partnumber": str(partnumber or "").strip().upper(),
            "status": "VALIDATION_ERROR",
            "error": str(exc),
        }


@mcp.tool()
def product_identity_derive_equivalents(
    after_id: int = 0,
    limit: int = 500,
    distributor: str | None = None,
    actor: str = "STECH_MCP",
) -> dict[str, Any]:
    """Procesa masivamente equivalencias UPC/EAN determinísticas antes del research web."""
    try:
        return product_identity_derivation_service.derive_batch(
            after_id=after_id,
            limit=limit,
            distributor=distributor,
            actor=actor,
        )
    except ValueError as exc:
        return {
            "after_id": max(0, int(after_id or 0)),
            "scanned_count": 0,
            "processed_partnumber_count": 0,
            "by_status": {"VALIDATION_ERROR": 1},
            "results": [],
            "has_more": False,
            "status": "VALIDATION_ERROR",
            "error": str(exc),
        }


@mcp.tool()
def product_identity_research_queue(
    after_id: int = 0,
    limit: int = 100,
    distributor: str | None = None,
    include_deferred: bool = False,
) -> dict[str, Any]:
    """Devuelve la cola masiva reanudable y omite casos terminales o identidades inválidas ya conocidas."""
    try:
        return product_identity_research_service.queue(
            after_id=after_id,
            limit=limit,
            distributor=distributor,
            include_deferred=include_deferred,
        )
    except ValueError as exc:
        return {"status": "VALIDATION_ERROR", "error": str(exc), "products": [], "count": 0}


@mcp.tool()
def product_identity_research_record(
    producto_distribuidor_id: int,
    partnumber: str,
    identifier_type: str,
    status: str,
    note: str | None = None,
    value_text: str | None = None,
    confidence_grade: str | None = None,
    source_url: str | None = None,
    source_type: str | None = None,
    source_partnumber: str | None = None,
    evidence_text: str | None = None,
    approved_by: str = "CHATGPT",
) -> dict[str, Any]:
    """Registra un resultado de research; VERIFIED verifica y promueve en una sola llamada."""
    try:
        return product_identity_research_service.record(
            producto_distribuidor_id=producto_distribuidor_id,
            partnumber=partnumber,
            identifier_type=identifier_type,
            status=status,
            note=note,
            value_text=value_text,
            confidence_grade=confidence_grade,
            source_url=source_url,
            source_type=source_type,
            source_partnumber=source_partnumber,
            evidence_text=evidence_text,
            approved_by=approved_by,
        )
    except ValueError as exc:
        return {
            "recorded": False,
            "status": "VALIDATION_ERROR",
            "partnumber": str(partnumber or "").strip().upper(),
            "identifier_type": str(identifier_type or "").strip().upper(),
            "error": str(exc),
            "retryable": True,
        }


@mcp.tool()
def product_identity_research_record_batch(
    items: list[dict[str, Any]],
    approved_by: str = "CHATGPT",
) -> dict[str, Any]:
    """Registra hasta 100 resultados de research en una llamada y continúa aunque un elemento sea inválido."""
    try:
        return product_identity_research_service.record_batch(items, approved_by=approved_by)
    except ValueError as exc:
        return {
            "count": 0,
            "recorded_count": 0,
            "error_count": 1,
            "by_status": {"VALIDATION_ERROR": 1},
            "results": [],
            "status": "VALIDATION_ERROR",
            "error": str(exc),
        }


@mcp.tool()
def product_identity_research_status(partnumber: str | None = None) -> dict[str, Any]:
    """Resume estados persistidos del research masivo, globalmente o por Part Number."""
    return product_identity_research_service.status(partnumber=partnumber)


@mcp.tool()
def product_images_get(partnumber: str) -> dict[str, Any]:
    """Lee imágenes reales de Deltron y variantes del Workspace sin exigir edición de imágenes."""
    normalized = partnumber.strip().upper()
    product = product_repository.get_by_partnumber(normalized)
    if product is None:
        return {
            "found": False,
            "partnumber": normalized,
            "source_image_count": 0,
            "workspace_image_count": 0,
            "image_count": 0,
            "usable_image_count": 0,
            "approved_image_count": 0,
            "images": [],
        }

    source_product_id = product.get("producto_distribuidor_id")
    source_rows = (
        deltron_image_repository.list_for_product(int(source_product_id))
        if source_product_id is not None
        else []
    )
    source_images = normalize_deltron_images(normalized, source_rows)
    workspace_images = product_master_repository.list_images(normalized)
    images = [*source_images, *workspace_images]
    usable = sum(
        1
        for image in images
        if bool(image.get("is_approved")) or bool(image.get("source_eligible"))
    )
    approved = sum(1 for image in images if bool(image.get("is_approved")))

    return {
        "found": True,
        "partnumber": normalized,
        "producto_distribuidor_id": source_product_id,
        "source_table": "DB_DISTRIBUIDORES.dbo.PRD_DELTRON_IMAGEN",
        "source_image_count": len(source_images),
        "workspace_image_count": len(workspace_images),
        "image_count": len(images),
        "usable_image_count": usable,
        "approved_image_count": approved,
        "editing_required": False,
        "source_images": source_images,
        "workspace_images": workspace_images,
        "images": images,
    }


def main() -> None:
    if settings.mcp_transport == "stdio":
        mcp.run()
        return

    import uvicorn

    security = build_transport_security(settings)
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
