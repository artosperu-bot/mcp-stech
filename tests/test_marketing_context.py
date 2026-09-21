from stech_mcp.services.marketing_context import MarketingProductContextService


class Products:
    def __init__(self, *, history_error=False):
        self.history_error = history_error

    def list_by_partnumber(self, pn, limit=100):
        return [
            {
                "part_number": pn,
                "producto_distribuidor_id": 11,
                "distribuidor": "DELTRON",
                "marca": "ULEFONE",
                "nombre": "Armor 25T Pro",
                "ean": "1234567890123",
                "stock_valor": 7,
                "precio_actual_usd": 299,
                "ultima_observacion": "2026-09-21T10:00:00",
            },
            {
                "part_number": pn,
                "producto_distribuidor_id": 12,
                "distribuidor": "INGRAM",
                "marca": "ULEFONE",
                "nombre": "Armor 25T Pro",
                "ean": "1234567890123",
                "stock_valor": 4,
                "precio_actual_usd": 305,
                "ultima_observacion": "2026-09-21T09:55:00",
            },
        ][:limit]

    def get_by_partnumber(self, pn):
        rows = self.list_by_partnumber(pn, limit=1)
        return rows[0] if rows else None

    def history(self, pn, limit=1):
        if self.history_error:
            raise RuntimeError("history unavailable")
        return [{"part_number": pn, "stock_valor": 7, "observado_at": "2026-09-21T10:00:00"}]


class Workspace:
    def __init__(self, *, image_state="READY", exact_count=2, conflicts=0, missing=None):
        self.image_state = image_state
        self.exact_count = exact_count
        self.conflicts = conflicts
        self.missing = list(missing or [])

    def get(self, pn):
        return {
            "found": True,
            "master": {
                "partnumber": pn,
                "brand": "ULEFONE",
                "name": "Armor 25T Pro",
                "ean": "1234567890123",
            },
            "technical": {
                "state": "READY",
                "missing_required": self.missing,
                "completion_pct": 100,
            },
            "images": {
                "readiness": {
                    "state": self.image_state,
                    "image_count": 3,
                    "exact_count": self.exact_count,
                }
            },
            "evidence": {"conflict_count": self.conflicts},
        }


class SourceImages:
    def list_for_product(self, product_id):
        if product_id == 11:
            return [
                {
                    "part_number_snapshot": "ARMOR25T",
                    "url_origen": "https://example.test/armor-deltron.jpg",
                    "orden_imagen": 1,
                }
            ]
        if product_id == 12:
            return [
                {
                    "part_number_snapshot": "ARMOR25T",
                    "url_origen": "https://example.test/armor-ingram.jpg",
                    "orden_imagen": 1,
                }
            ]
        return []


class WorkspaceImages:
    def list_images(self, pn):
        return [
            {
                "partnumber": pn,
                "is_approved": True,
                "position": 1,
                "local_path": r"C:\\STECH_IMAGENES\\armor.jpg",
            }
        ]


def build(*, workspace=None, products=None):
    return MarketingProductContextService(
        product_repository=products or Products(),
        workspace_service=workspace or Workspace(),
        source_image_repository=SourceImages(),
        workspace_image_repository=WorkspaceImages(),
    )


def test_marketing_context_is_read_only_and_does_not_promote_source_price_to_selling_price():
    result = build().get("armor25t")

    assert result["found"] is True
    assert result["partnumber"] == "ARMOR25T"
    assert result["operational"]["current"]["precio_actual_usd"] == 299
    assert result["operational"]["distributor_count"] == 2
    assert [row["distribuidor"] for row in result["operational"]["distributors"]] == ["DELTRON", "INGRAM"]
    assert result["operational"]["selling_price_authoritative"] is False
    assert result["safety"]["read_only"] is True
    assert result["safety"]["meta_write_authority"] is False


def test_marketing_readiness_blocks_conflicts_missing_required_and_non_exact_media():
    result = build(
        workspace=Workspace(
            image_state="REVIEW_REQUIRED",
            exact_count=0,
            conflicts=1,
            missing=["cpu_model"],
        )
    ).readiness("armor25t")

    assert result["state"] == "BLOCKED"
    assert result["creative_generation_allowed"] is False
    assert result["publication_allowed"] is False
    assert "TECHNICAL_REQUIRED_FIELDS_MISSING" in result["blockers"]
    assert "FACT_CONFLICTS_PRESENT" in result["blockers"]
    assert "PRODUCT_IMAGES_REQUIRE_REVIEW" in result["blockers"]
    assert "NO_EXACT_PRODUCT_REFERENCE_IMAGE" in result["blockers"]


def test_media_manifest_enables_product_lock_when_an_approved_reference_exists():
    result = build().media_manifest("armor25t")

    assert result["found"] is True
    assert result["product_lock"]["enabled"] is True
    assert result["product_lock"]["policy"] == "PRESERVE_PRODUCT_IDENTITY"
    assert result["product_lock"]["reference_count"] == 3
    assert {row["media_source"] for row in result["references"]} == {"DISTRIBUTOR_DB", "STECH_WORKSPACE"}
    assert {row.get("distributor") for row in result["source_images"]} == {"DELTRON", "INGRAM"}


def test_history_failure_does_not_break_marketing_context():
    result = build(products=Products(history_error=True)).get("armor25t")

    assert result["found"] is True
    assert result["operational"]["latest_observation"] is None
    assert "RuntimeError" in result["operational"]["history_error"]
