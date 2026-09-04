import json
from decimal import Decimal

from stech_mcp.services.product_prepare import ProductPrepareService


class FakeProductRepository:
    def __init__(self, product):
        self.product = product
        self.calls = []

    def get_by_partnumber(self, partnumber):
        self.calls.append(partnumber)
        return self.product


class FakeEnrichmentRepository:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def get_approved(self, partnumber, field_codes=None):
        self.calls.append((partnumber, tuple(field_codes) if field_codes else None))
        if field_codes:
            wanted = set(field_codes)
            return [row for row in self.rows if row.get("field_code") in wanted]
        return list(self.rows)


class FakePackagingRuleRepository:
    def match(self, category_code, screen_inches):
        assert category_code == "LAPTOP"
        assert screen_inches == Decimal("15.6")
        return {
            "rule_code": "LAPTOP_15_X_DEFAULT",
            "width_cm": Decimal("33.00"),
            "length_cm": Decimal("54.00"),
            "height_cm": Decimal("7.00"),
            "weight_g": 2500,
            "source_code": "REGLA_STECH_EMPAQUE",
        }


class FakeSourceImageRepository:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def list_for_product(self, producto_distribuidor_id):
        self.calls.append(producto_distribuidor_id)
        return list(self.rows)


class FakeProductMasterRepository:
    def __init__(self):
        self.snapshots = []
        self.drafts = []
        self.audit = []
        self.images = []

    def upsert_master(self, snapshot):
        self.snapshots.append(snapshot)
        return snapshot

    def replace_draft(self, **kwargs):
        self.drafts.append(kwargs)
        return {
            "channel_draft_id": 9,
            "draft_version": 1,
            "field_count": len(kwargs["payload"]["fields"]),
            "required_missing_count": len(kwargs["payload"].get("ready_for_research", [])),
            "estimated_count": len(kwargs["payload"].get("estimated_fields", [])),
            "status": "FALTAN_DATOS",
        }

    def list_images(self, partnumber):
        return self.images

    def add_audit_event(self, **kwargs):
        self.audit.append(kwargs)


def _product():
    return {
        "producto_distribuidor_id": 1162,
        "distribuidor": "DELTRON",
        "part_number": "82YU00XYLM",
        "upc": "197528523880",
        "mini_codigo": "418120",
        "marca": "LENOVO",
        "nombre": 'LAPTOP LENOVO V15 G4 AMN 15.6" RYZEN 5 7520U 16GB',
        "precio_usd_sin_igv": 701,
        "stock_valor": 20,
        "stock_operador": ">",
        "observado_at": "2026-09-04T11:41:34",
        "atributos_json": json.dumps(
            {
                "especificaciones": {
                    "MODELO": "V15 G4 AMN",
                    "PANTALLA": '15.6 PULG FHD TN 1920 X 1080',
                    "CPU": "AMD RYZEN 5 7520U",
                    "PESO": "1.65 KG",
                    "COMENTARIOS": "COLOR ARTIC GREY ADAPTADOR DE PODER 65W ROUND TIP (3-PIN)",
                }
            }
        ),
    }


def test_prepare_persists_product_master_package_and_81_field_coolbox_draft():
    product_repo = FakeProductRepository(_product())
    master_repo = FakeProductMasterRepository()
    service = ProductPrepareService(
        product_repository=product_repo,
        enrichment_repository=FakeEnrichmentRepository(),
        packaging_rule_repository=FakePackagingRuleRepository(),
        product_master_repository=master_repo,
    )

    result = service.prepare("82yu00xylm")

    assert result["found"] is True
    assert product_repo.calls == ["82YU00XYLM"]
    assert result["package"]["weight_g"] == 2500
    assert result["package"]["rule_code"] == "LAPTOP_15_X_DEFAULT"
    assert result["coolbox_preview"]["field_count"] == 81
    assert len(master_repo.drafts) == 1
    assert len(master_repo.drafts[0]["payload"]["fields"]) == 81
    assert master_repo.snapshots[0]["package_width_cm"] == Decimal("33.00")
    assert master_repo.snapshots[0]["package_length_cm"] == Decimal("54.00")
    assert master_repo.snapshots[0]["package_height_cm"] == Decimal("7.00")
    assert master_repo.snapshots[0]["package_weight_g"] == 2500
    assert master_repo.audit[0]["event_type"] == "PRODUCT_PREPARED"


def test_prepare_applies_all_approved_enrichments_to_persisted_coolbox_draft():
    enrichments = FakeEnrichmentRepository([
        {
            "field_code": "ssd_capacity_gb",
            "value_number": Decimal("512"),
            "value_text": None,
            "unit": "GB",
            "method": "VERIFIED",
            "confidence_grade": "A1",
            "is_approved": True,
        }
    ])
    master_repo = FakeProductMasterRepository()
    service = ProductPrepareService(
        product_repository=FakeProductRepository(_product()),
        enrichment_repository=enrichments,
        packaging_rule_repository=FakePackagingRuleRepository(),
        product_master_repository=master_repo,
    )

    result = service.prepare("82YU00XYLM")

    fields = {row["field"]: row for row in result["coolbox_preview"]["fields"]}
    assert fields["Capacidad de disco sólido (SSD)"]["value"] == "512 GB"
    assert fields["Capacidad de disco sólido (SSD)"]["status"] == "VERIFIED"
    persisted_fields = {row["field"]: row for row in master_repo.drafts[0]["payload"]["fields"]}
    assert persisted_fields["Capacidad de disco sólido (SSD)"]["value"] == "512 GB"
    assert ("82YU00XYLM", None) in enrichments.calls


def test_prepare_uses_exact_deltron_source_images_without_requiring_editing():
    source_rows = [
        {
            "imagen_id": 10 + i,
            "producto_distribuidor_id": 1162,
            "orden_imagen": i + 1,
            "url_origen": f"https://imagenes.deltron.com.pe/82YU00XYLM/{i + 1}.jpg",
            "part_number_snapshot": "82YU00XYLM",
            "ruta_actual": fr"C:\STECH_IMAGENES\82YU00XYLM\{i + 1}.jpg",
            "nombre_archivo": f"{i + 1}.jpg",
            "ancho_px": 1200,
            "alto_px": 1200,
            "formato": "jpg",
            "hash_sha256": str(i) * 64,
            "fecha_eliminacion": None,
        }
        for i in range(4)
    ]
    source_repo = FakeSourceImageRepository(source_rows)
    master_repo = FakeProductMasterRepository()
    service = ProductPrepareService(
        product_repository=FakeProductRepository(_product()),
        enrichment_repository=FakeEnrichmentRepository(),
        packaging_rule_repository=FakePackagingRuleRepository(),
        product_master_repository=master_repo,
        source_image_repository=source_repo,
    )

    result = service.prepare("82YU00XYLM")

    assert source_repo.calls == [1162]
    assert len(result["source_images"]) == 4
    assert result["source_images"][0]["source_type"] == "DELTRON_DB"
    assert result["source_images"][0]["editing_required"] is False
    assert result["readiness"]["usable_image_count"] == 4
    assert result["readiness"]["image_score"] == 100
    assert result["readiness"]["state"] != "FALTAN_IMAGENES"


def test_prepare_missing_product_does_not_persist_anything():
    product_repo = FakeProductRepository(None)
    master_repo = FakeProductMasterRepository()
    service = ProductPrepareService(
        product_repository=product_repo,
        enrichment_repository=FakeEnrichmentRepository(),
        packaging_rule_repository=FakePackagingRuleRepository(),
        product_master_repository=master_repo,
    )

    result = service.prepare("NO-EXISTE")

    assert result == {"found": False, "partnumber": "NO-EXISTE"}
    assert master_repo.snapshots == []
    assert master_repo.drafts == []
    assert master_repo.audit == []
